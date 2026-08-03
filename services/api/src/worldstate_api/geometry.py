# pyright: basic, reportAttributeAccessIssue=false, reportMissingImports=false, reportMissingTypeStubs=false
"""Video inspection, keyframe selection, and optional metric reconstruction."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import cv2
import numpy as np

from worldstate_api.artifacts import ArtifactStore
from worldstate_api.capture import score_quality
from worldstate_api.jobs import JobCancelled, JobContext
from worldstate_api.providers.map_anything import load_map_anything_local
from worldstate_api.providers.registry import ModelManifestError, ModelRegistry
from worldstate_api.runtime import GpuScheduler


class MediaValidationError(ValueError):
    pass


def _binary_export(value: object, *, file_type: str) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray | memoryview):
        return bytes(value)
    raise RuntimeError(f"trimesh {file_type} export did not produce binary data")


class ReconstructionUnavailable(RuntimeError):
    pass


def _map_anything_worker(
    model_path: str,
    image_paths: tuple[str, ...],
    output_path: str,
    error_path: str,
) -> None:
    """Run untrusted-heavy geometry code behind a cancellable process boundary."""

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    model: Any = None
    try:
        import torch
        from mapanything.utils.image import load_images

        model = load_map_anything_local(Path(model_path), device="cuda")
        views = load_images(list(image_paths))
        with torch.inference_mode():
            predictions = model.infer(
                views,
                memory_efficient_inference=True,
                minibatch_size=1,
                use_amp=True,
                amp_dtype="fp16",
                apply_mask=True,
                mask_edges=True,
                apply_confidence_mask=True,
                confidence_percentile=10,
            )
        point_parts: list[np.ndarray] = []
        confidence_parts: list[np.ndarray] = []
        for prediction in predictions:
            points = prediction["pts3d"].detach().float().cpu().numpy().reshape(-1, 3)
            confidence = prediction["conf"].detach().float().cpu().numpy().reshape(-1)
            mask = prediction["mask"].detach().cpu().numpy().reshape(-1).astype(bool)
            point_parts.append(points[mask])
            confidence_parts.append(confidence[mask])
        if not point_parts or not any(len(part) for part in point_parts):
            raise RuntimeError("MapAnything produced no usable geometry")
        points = np.concatenate(point_parts)
        confidences = np.concatenate(confidence_parts)
        if len(points) > 500_000:
            indices = np.linspace(0, len(points) - 1, 500_000, dtype=np.int64)
            points = points[indices]
            confidences = confidences[indices]
        np.savez_compressed(
            output_path,
            points=points.astype(np.float32),
            confidences=confidences.astype(np.float32),
        )
    except Exception as error:
        error_type = type(error).__name__
        category = (
            "cuda_out_of_memory"
            if error_type in {"OutOfMemoryError", "CUDAOutOfMemoryError"}
            else "inference_failed"
        )
        Path(error_path).write_text(
            json.dumps({"category": category, "error_type": error_type}),
            encoding="utf-8",
        )
    finally:
        if model is not None:
            del model
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    width: int
    height: int
    frame_count: int
    fps: float
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class Keyframe:
    frame_index: int
    timestamp_seconds: float
    image_bgr: np.ndarray
    quality: dict[str, float]


def _open_bounded_video(path: Path) -> cv2.VideoCapture:
    """Open FFmpeg with native open/read deadlines for hostile local media."""

    capture = cv2.VideoCapture(
        str(path),
        cv2.CAP_FFMPEG,
        [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
            5_000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            5_000,
        ],
    )
    if not capture.isOpened():
        capture.release()
        raise MediaValidationError("the uploaded video cannot be decoded")
    return capture


def inspect_video(path: Path, *, maximum_duration_seconds: int) -> VideoMetadata:
    capture = _open_bounded_video(path)
    try:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if width <= 0 or height <= 0 or frame_count <= 0 or not 0.1 <= fps <= 240.0:
            raise MediaValidationError("the uploaded video metadata is invalid")
        duration = frame_count / fps
        if duration > maximum_duration_seconds:
            raise MediaValidationError("the uploaded video exceeds the duration limit")
        return VideoMetadata(width, height, frame_count, fps, duration)
    finally:
        capture.release()


def select_keyframes(
    path: Path,
    metadata: VideoMetadata,
    *,
    maximum_keyframes: int = 48,
) -> tuple[Keyframe, ...]:
    capture = _open_bounded_video(path)
    selected: list[Keyframe] = []
    sample_stride = max(1, metadata.frame_count // (maximum_keyframes * 4))
    orb = cv2.ORB_create(nfeatures=800)
    previous_descriptors: np.ndarray | None = None
    try:
        frame_index = 0
        while len(selected) < maximum_keyframes:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % sample_stride != 0:
                frame_index += 1
                continue
            quality = score_quality(frame)
            if quality["keyframe_score"] < 0.28:
                frame_index += 1
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            _, descriptors = orb.detectAndCompute(gray, None)
            sufficiently_new = previous_descriptors is None
            if descriptors is not None and previous_descriptors is not None:
                matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
                matches = matcher.match(previous_descriptors, descriptors)
                median_distance = (
                    float(np.median([match.distance for match in matches])) if matches else 255.0
                )
                sufficiently_new = median_distance >= 24.0
            if sufficiently_new:
                selected.append(
                    Keyframe(
                        frame_index=frame_index,
                        timestamp_seconds=frame_index / metadata.fps,
                        image_bgr=frame.copy(),
                        quality=quality,
                    )
                )
                previous_descriptors = descriptors
            frame_index += 1
    finally:
        capture.release()
    if len(selected) < 2:
        raise MediaValidationError("the video does not contain enough distinct usable views")
    return tuple(selected)


class ScanPipeline:
    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        model_registry: ModelRegistry,
        scheduler: GpuScheduler,
        work_root: Path,
        maximum_duration_seconds: int,
        suspend_live_provider: Callable[[], None] | None = None,
        resume_live_provider: Callable[[], None] | None = None,
    ) -> None:
        self.artifact_store = artifact_store
        self.model_registry = model_registry
        self.scheduler = scheduler
        self.work_root = work_root.resolve()
        self.maximum_duration_seconds = maximum_duration_seconds
        self.suspend_live_provider = suspend_live_provider or (lambda: None)
        self.resume_live_provider = resume_live_provider or (lambda: None)
        self.work_root.mkdir(parents=True, exist_ok=True)

    def run(self, context: JobContext) -> dict[str, object]:
        artifact_id = str(context.parameters.get("video_artifact_id", ""))
        if not artifact_id:
            raise MediaValidationError("scan jobs require video_artifact_id")
        video_path = self.artifact_store.resolve_trusted_path(artifact_id)
        context.update(progress=0.05, stage="validating_media")
        metadata = inspect_video(
            video_path,
            maximum_duration_seconds=self.maximum_duration_seconds,
        )
        context.check_cancelled()
        context.update(progress=0.15, stage="selecting_keyframes")
        keyframes = select_keyframes(video_path, metadata)
        context.check_cancelled()

        keyframe_artifact_ids: list[str] = []
        with tempfile.TemporaryDirectory(prefix="scan-", dir=self.work_root) as directory:
            scan_directory = Path(directory)
            image_paths: list[Path] = []
            for index, keyframe in enumerate(keyframes):
                encoded, jpeg = cv2.imencode(
                    ".jpg",
                    keyframe.image_bgr,
                    [cv2.IMWRITE_JPEG_QUALITY, 92],
                )
                if not encoded:
                    raise RuntimeError("failed to encode a selected keyframe")
                stored = self.artifact_store.put_bytes(
                    bytes(jpeg),
                    media_type="image/jpeg",
                    kind="scan-keyframe",
                    scene_id=context.scene_id,
                    job_id=context.job_id,
                    purpose=f"scan-keyframe:{index}",
                )
                keyframe_artifact_ids.append(stored.id)
                image_path = scan_directory / f"frame-{index:04d}.jpg"
                image_path.write_bytes(bytes(jpeg))
                image_paths.append(image_path)

            context.update(progress=0.35, stage="waiting_for_gpu")
            try:
                with self.scheduler.exclusive(context.cancellation):
                    try:
                        self.suspend_live_provider()
                        context.update(progress=0.40, stage="reconstructing")
                        try:
                            reconstruction = self._reconstruct(image_paths, context)
                        except ModelManifestError:
                            context.update(
                                progress=0.48,
                                stage="reconstructing_depth_fallback",
                            )
                            try:
                                reconstruction = self._depth_fallback(
                                    image_paths,
                                    context,
                                    started=perf_counter(),
                                    reason="verified_map_anything_model_unavailable",
                                )
                            except JobCancelled:
                                raise
                            except Exception as error:
                                raise ReconstructionUnavailable(
                                    "verified_reconstruction_models_unavailable"
                                ) from error
                    finally:
                        self.resume_live_provider()
            except (ModelManifestError, ReconstructionUnavailable) as error:
                reconstruction = {
                    "status": "degraded",
                    "quality": "keyframes_only",
                    "reason": str(error),
                    "artifact_ids": [],
                    "approximate_scale": True,
                }

        context.update(progress=0.90, stage="active_scan_analysis")
        average_quality = float(np.mean([frame.quality["keyframe_score"] for frame in keyframes]))
        coach = self._coach(metadata, keyframes, average_quality)
        manifest = {
            "schema_version": 1,
            "scene_id": context.scene_id,
            "source_video_artifact_id": artifact_id,
            "video": {
                "width": metadata.width,
                "height": metadata.height,
                "fps": metadata.fps,
                "duration_seconds": metadata.duration_seconds,
            },
            "keyframes": [
                {
                    "artifact_id": keyframe_artifact_ids[index],
                    "frame_index": frame.frame_index,
                    "timestamp_seconds": frame.timestamp_seconds,
                    "quality": frame.quality,
                }
                for index, frame in enumerate(keyframes)
            ],
            "reconstruction": reconstruction,
            "active_scan_coach": coach,
        }
        manifest_artifact = self.artifact_store.put_bytes(
            json.dumps(manifest, sort_keys=True, indent=2).encode(),
            media_type="application/json",
            kind="scan-manifest",
            scene_id=context.scene_id,
            job_id=context.job_id,
            purpose="scan-manifest",
        )
        context.update(progress=0.98, stage="finalizing")
        return {
            "status": reconstruction["status"],
            "manifest_artifact_id": manifest_artifact.id,
            "geometry_artifact_ids": reconstruction.get("artifact_ids", []),
            "keyframe_count": len(keyframes),
            "approximate_scale": reconstruction.get("approximate_scale", True),
            "active_scan_coach": coach,
        }

    def _reconstruct(
        self,
        image_paths: list[Path],
        context: JobContext,
    ) -> dict[str, object]:
        model_path = self.model_registry.trusted_path("map-anything-apache")
        started = perf_counter()
        reconstruction_paths = self._bounded_reconstruction_paths(image_paths)
        output_path = image_paths[0].parent / "map-anything-output.npz"
        error_path = image_paths[0].parent / "map-anything-error.json"
        process = mp.get_context("spawn").Process(
            target=_map_anything_worker,
            args=(
                str(model_path),
                tuple(str(path) for path in reconstruction_paths),
                str(output_path),
                str(error_path),
            ),
            name="worldstate-reconstruction",
            daemon=True,
        )
        process.start()
        try:
            while process.is_alive():
                process.join(timeout=0.25)
                context.check_cancelled()
        except JobCancelled:
            if process.is_alive():
                process.terminate()
            process.join(timeout=10)
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
            raise
        process.join(timeout=1)
        if error_path.is_file():
            error_payload = json.loads(error_path.read_text(encoding="utf-8"))
            if error_payload.get("category") == "cuda_out_of_memory":
                context.update(progress=0.48, stage="reconstructing_depth_fallback")
                try:
                    return self._depth_fallback(
                        image_paths,
                        context,
                        started=started,
                        reason="map_anything_gpu_memory_exhausted",
                    )
                except JobCancelled:
                    raise
                except Exception as error:
                    raise ReconstructionUnavailable(
                        "map_anything_and_depth_fallback_unavailable"
                    ) from error
            raise ReconstructionUnavailable("map_anything_inference_failed")
        if process.exitcode != 0 or not output_path.is_file():
            raise ReconstructionUnavailable("map_anything_worker_exited")
        with np.load(output_path, allow_pickle=False) as result:
            points = np.asarray(result["points"], dtype=np.float32)
            confidences = np.asarray(result["confidences"], dtype=np.float32)
        confidence_normalized = (confidences - confidences.min()) / max(
            float(np.ptp(confidences)), 1e-6
        )
        colors = cv2.applyColorMap(
            (confidence_normalized * 255).astype(np.uint8),
            cv2.COLORMAP_TURBO,
        )[:, 0, ::-1]
        points, colors = self._clean_cloud(points, colors)
        artifacts = self._store_cloud(
            points,
            colors,
            context=context,
            purpose_prefix="scan",
        )
        return {
            "status": "succeeded",
            "quality": "map_anything_relative_scale",
            "artifact_ids": artifacts,
            "approximate_scale": True,
            "point_count": len(points),
            "inference_seconds": perf_counter() - started,
            "input_view_count": len(reconstruction_paths),
        }

    @staticmethod
    def _bounded_reconstruction_paths(
        image_paths: list[Path],
        *,
        maximum_views: int = 16,
    ) -> list[Path]:
        if len(image_paths) <= maximum_views:
            return image_paths
        indices = np.linspace(0, len(image_paths) - 1, maximum_views, dtype=np.int64)
        return [image_paths[int(index)] for index in indices]

    @staticmethod
    def _clean_cloud(
        points: np.ndarray,
        colors: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Voxel-fuse and remove statistical outliers with Open3D."""

        import open3d as o3d

        finite = np.isfinite(points).all(axis=1)
        points = np.asarray(points[finite], dtype=np.float64)
        colors = np.asarray(colors[finite], dtype=np.float64) / 255.0
        if len(points) < 2:
            raise RuntimeError("reconstruction produced insufficient finite geometry")
        cloud = o3d.geometry.PointCloud()
        cloud.points = o3d.utility.Vector3dVector(points)
        cloud.colors = o3d.utility.Vector3dVector(colors)
        extent = np.asarray(cloud.get_max_bound()) - np.asarray(cloud.get_min_bound())
        voxel_size = max(float(np.linalg.norm(extent)) / 700.0, 1e-4)
        cloud = cloud.voxel_down_sample(voxel_size)
        if len(cloud.points) >= 24:
            cloud, _ = cloud.remove_statistical_outlier(
                nb_neighbors=min(20, len(cloud.points) - 1),
                std_ratio=2.0,
            )
        cleaned_points = np.asarray(cloud.points, dtype=np.float32)
        cleaned_colors = np.clip(
            np.asarray(cloud.colors) * 255.0,
            0,
            255,
        ).astype(np.uint8)
        return cleaned_points, cleaned_colors

    def _depth_fallback(
        self,
        image_paths: list[Path],
        context: JobContext,
        *,
        started: float,
        reason: str,
    ) -> dict[str, object]:
        """Build approximate geometry from local relative depth and Open3D ICP."""

        try:
            import open3d as o3d
            import torch
            from PIL import Image
            from transformers import AutoImageProcessor, AutoModelForDepthEstimation
        except ImportError as error:
            raise ModelManifestError("depth fallback dependencies are unavailable") from error

        depth_path = self.model_registry.trusted_path("depth-anything-v2-small")
        processor = AutoImageProcessor.from_pretrained(depth_path, local_files_only=True)
        model = AutoModelForDepthEstimation.from_pretrained(
            depth_path,
            local_files_only=True,
        ).to("cuda")
        model.eval()
        paths = self._bounded_reconstruction_paths(image_paths, maximum_views=8)
        fused: Any = None
        try:
            for index, path in enumerate(paths):
                context.check_cancelled()
                image_bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if image_bgr is None:
                    continue
                height, width = image_bgr.shape[:2]
                image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                inputs = processor(images=Image.fromarray(image_rgb), return_tensors="pt")
                inputs = {key: value.to("cuda") for key, value in inputs.items()}
                with (
                    torch.inference_mode(),
                    torch.autocast(device_type="cuda", dtype=torch.float16),
                ):
                    predicted = model(**inputs).predicted_depth
                depth = (
                    torch.nn.functional.interpolate(
                        predicted.unsqueeze(1),
                        size=(height, width),
                        mode="bicubic",
                        align_corners=False,
                    )
                    .squeeze()
                    .float()
                    .cpu()
                    .numpy()
                )
                depth = depth - float(np.nanmin(depth))
                depth = depth / max(float(np.nanmedian(depth)), 1e-6)
                stride = max(2, min(height, width) // 160)
                ys, xs = np.mgrid[0:height:stride, 0:width:stride]
                sampled_depth = np.clip(depth[::stride, ::stride], 0.05, 5.0)
                focal = 0.9 * max(width, height)
                points = np.column_stack(
                    (
                        (xs.reshape(-1) - width / 2) / focal * sampled_depth.reshape(-1),
                        (height / 2 - ys.reshape(-1)) / focal * sampled_depth.reshape(-1),
                        sampled_depth.reshape(-1),
                    )
                )
                colors = image_rgb[::stride, ::stride].reshape(-1, 3) / 255.0
                finite = np.isfinite(points).all(axis=1)
                view_cloud = o3d.geometry.PointCloud()
                view_cloud.points = o3d.utility.Vector3dVector(points[finite])
                view_cloud.colors = o3d.utility.Vector3dVector(colors[finite])
                view_cloud = view_cloud.voxel_down_sample(0.015)
                if fused is None:
                    fused = view_cloud
                else:
                    registration = o3d.pipelines.registration.registration_icp(
                        view_cloud,
                        fused,
                        0.20,
                        np.eye(4),
                        o3d.pipelines.registration.TransformationEstimationPointToPoint(),
                        o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=35),
                    )
                    view_cloud.transform(registration.transformation)
                    fused += view_cloud
                    fused = fused.voxel_down_sample(0.015)
                context.update(
                    progress=0.48 + 0.30 * ((index + 1) / max(len(paths), 1)),
                    stage="reconstructing_depth_fallback",
                )
        finally:
            del model
            torch.cuda.empty_cache()
        if fused is None or len(fused.points) < 2:
            raise RuntimeError("depth fallback produced insufficient geometry")
        points = np.asarray(fused.points, dtype=np.float32)
        colors = np.clip(np.asarray(fused.colors) * 255.0, 0, 255).astype(np.uint8)
        points, colors = self._clean_cloud(points, colors)
        artifacts = self._store_cloud(
            points,
            colors,
            context=context,
            purpose_prefix="scan-depth-fallback",
        )
        return {
            "status": "degraded",
            "quality": "depth_assisted_open3d_relative_scale",
            "reason": reason,
            "artifact_ids": artifacts,
            "approximate_scale": True,
            "point_count": len(points),
            "inference_seconds": perf_counter() - started,
            "input_view_count": len(paths),
        }

    def _store_cloud(
        self,
        points: np.ndarray,
        colors: np.ndarray,
        *,
        context: JobContext,
        purpose_prefix: str,
    ) -> list[str]:
        import trimesh

        cloud = trimesh.points.PointCloud(points, colors=colors)
        ply_bytes = _binary_export(cloud.export(file_type="ply"), file_type="ply")
        glb_bytes = _binary_export(cloud.export(file_type="glb"), file_type="glb")
        ply_artifact = self.artifact_store.put_bytes(
            ply_bytes,
            media_type="model/ply",
            kind="point-cloud",
            scene_id=context.scene_id,
            job_id=context.job_id,
            purpose=f"{purpose_prefix}-point-cloud",
        )
        glb_artifact = self.artifact_store.put_bytes(
            glb_bytes,
            media_type="model/gltf-binary",
            kind="scene-geometry",
            scene_id=context.scene_id,
            job_id=context.job_id,
            purpose=f"{purpose_prefix}-geometry",
        )
        return [glb_artifact.id, ply_artifact.id]

    @staticmethod
    def _coach(
        metadata: VideoMetadata,
        keyframes: tuple[Keyframe, ...],
        average_quality: float,
    ) -> list[dict[str, object]]:
        suggestions: list[dict[str, object]] = []
        if average_quality < 0.5:
            suggestions.append(
                {
                    "kind": "improve_lighting_or_slow_down",
                    "confidence": 0.85,
                    "message": "Improve lighting and move the camera more slowly.",
                }
            )
        views_per_second = len(keyframes) / max(metadata.duration_seconds, 0.01)
        if views_per_second < 0.25:
            suggestions.append(
                {
                    "kind": "increase_view_coverage",
                    "confidence": 0.78,
                    "message": "Revisit the scene from additional angles.",
                }
            )
        if not suggestions:
            suggestions.append(
                {
                    "kind": "coverage_acceptable",
                    "confidence": 0.72,
                    "message": "Coverage is suitable for reconstruction.",
                }
            )
        return suggestions
