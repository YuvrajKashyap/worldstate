# pyright: basic, reportMissingImports=false
"""Measured GPU smoke tests for WorldState's pinned local model providers."""

from __future__ import annotations

import argparse
import gc
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from worldstate_api.providers.map_anything import load_map_anything_local
from worldstate_api.providers.models import ModelBundleProvider
from worldstate_api.providers.registry import ModelRegistry
from worldstate_api.providers.supervised import SupervisedPerceptionProvider
from worldstate_api.settings import Settings


def _registry() -> ModelRegistry:
    settings = Settings()
    return ModelRegistry(
        manifest_path=settings.model_manifest_path,
        lock_path=settings.model_lock_path,
        models_root=settings.models_root,
    )


def _synthetic_frame(*, shift_x: int = 0) -> np.ndarray:
    image = np.full((360, 640, 3), 235, dtype=np.uint8)
    cv2.rectangle(image, (70, 145), (180, 290), (30, 70, 180), thickness=-1)
    cv2.rectangle(image, (245, 185), (430, 285), (50, 150, 60), thickness=-1)
    cv2.circle(image, (520, 215), 58, (180, 80, 35), thickness=-1)
    cv2.putText(
        image,
        "WorldState GPU smoke",
        (48, 70),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (20, 20, 20),
        2,
        cv2.LINE_AA,
    )
    if shift_x == 0:
        return image
    transform = np.asarray([[1.0, 0.0, float(shift_x)], [0.0, 1.0, 0.0]])
    return cv2.warpAffine(
        image,
        transform,
        (image.shape[1], image.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(235, 235, 235),
    )


def _centers_by_label(result: Any) -> dict[str, tuple[float, float]]:
    centers: dict[str, tuple[float, float]] = {}
    for observation in result.observations:
        x1, y1, x2, y2 = observation.box_xyxy
        centers.setdefault(observation.label, ((x1 + x2) / 2.0, (y1 + y2) / 2.0))
    return centers


def _cuda_memory(torch_module: Any) -> dict[str, float]:
    cuda = torch_module.cuda
    return {
        "allocated_mib": cuda.memory_allocated() / (1024 * 1024),
        "reserved_mib": cuda.memory_reserved() / (1024 * 1024),
        "peak_allocated_mib": cuda.max_memory_allocated() / (1024 * 1024),
        "peak_reserved_mib": cuda.max_memory_reserved() / (1024 * 1024),
    }


def smoke_live() -> dict[str, object]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    provider = ModelBundleProvider(_registry())
    started = time.perf_counter()
    try:
        result = provider.observe(
            _synthetic_frame(),
            sequence=0,
            prompts=("cup", "book", "phone"),
        )
        torch.cuda.synchronize()
        return {
            "status": "passed",
            "scope": "default live model bundle on a synthetic 640x360 frame",
            "provider": provider.provider_id,
            "wall_time_seconds": time.perf_counter() - started,
            "provider_inference_ms": result.inference_ms,
            "observation_count": len(result.observations),
            "discovery_ran": result.discovery_ran,
            "depth_ran": result.depth_ran,
            "embedding_ran": result.embedding_ran,
            "cuda": _cuda_memory(torch),
        }
    finally:
        provider.close()
        del provider
        gc.collect()
        torch.cuda.empty_cache()


def benchmark_live(frames: int) -> dict[str, object]:
    import torch

    if frames < 10:
        raise ValueError("live benchmark requires at least 10 frames")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    provider = ModelBundleProvider(_registry())
    image = _synthetic_frame()
    samples_ms: list[float] = []
    discovery_frames = 0
    depth_frames = 0
    embedding_frames = 0
    mask_refresh_frames = 0
    started = time.perf_counter()
    try:
        cold_started = time.perf_counter()
        initial = provider.observe(
            image,
            sequence=0,
            prompts=("cup", "book", "phone"),
        )
        torch.cuda.synchronize()
        cold_start_ms = (time.perf_counter() - cold_started) * 1000.0
        baseline_centers = _centers_by_label(initial)
        if not baseline_centers:
            raise RuntimeError("live benchmark discovered no objects on its first frame")
        center_errors_px: list[float] = []
        identity_coverages: list[float] = []
        previous_centers = baseline_centers
        tracked_motion_px: list[float] = []
        for sequence in range(1, frames + 1):
            shift_x = round(28.0 * np.sin(sequence * 0.08))
            before = time.perf_counter()
            result = provider.observe(
                _synthetic_frame(shift_x=shift_x),
                sequence=sequence,
                prompts=("cup", "book", "phone"),
            )
            torch.cuda.synchronize()
            samples_ms.append((time.perf_counter() - before) * 1000.0)
            centers = _centers_by_label(result)
            matched_labels = baseline_centers.keys() & centers.keys()
            identity_coverages.append(len(matched_labels) / len(baseline_centers))
            for label in matched_labels:
                expected_x = baseline_centers[label][0] + shift_x
                center_errors_px.append(abs(centers[label][0] - expected_x))
                previous = previous_centers.get(label)
                if previous is not None:
                    tracked_motion_px.append(abs(centers[label][0] - previous[0]))
            previous_centers = centers
            discovery_frames += int(result.discovery_ran)
            depth_frames += int(result.depth_ran)
            embedding_frames += int(result.embedding_ran)
            mask_refresh_frames += int(result.diagnostics.get("mask_refresh", 0))
        measured_seconds = sum(samples_ms) / 1000.0
        return {
            "status": "passed",
            "scope": "sequential adaptive live provider benchmark; synthetic frames",
            "frames": frames,
            "cold_start_ms": cold_start_ms,
            "wall_time_seconds_including_load": time.perf_counter() - started,
            "measured_inference_seconds": measured_seconds,
            "throughput_fps": frames / measured_seconds,
            "latency_ms": {
                "mean": float(np.mean(samples_ms)),
                "p50": float(np.percentile(samples_ms, 50)),
                "p95": float(np.percentile(samples_ms, 95)),
                "maximum": max(samples_ms),
            },
            "scheduler": {
                "discovery_frames": discovery_frames,
                "depth_frames": depth_frames,
                "embedding_frames": embedding_frames,
                "mask_refresh_frames": mask_refresh_frames,
            },
            "tracking": {
                "initial_labels": sorted(baseline_centers),
                "mean_identity_coverage": float(np.mean(identity_coverages)),
                "mean_center_error_px": float(np.mean(center_errors_px)),
                "p95_center_error_px": float(np.percentile(center_errors_px, 95)),
                "mean_tracked_motion_px_per_frame": float(np.mean(tracked_motion_px)),
            },
            "cuda": _cuda_memory(torch),
        }
    finally:
        provider.close()
        del provider
        gc.collect()
        torch.cuda.empty_cache()


def smoke_supervised_worker() -> dict[str, object]:
    """Exercise warm-up, shared-memory inference, reset, and clean teardown."""

    provider = SupervisedPerceptionProvider(_registry())
    image = _synthetic_frame()
    started = time.perf_counter()
    try:
        warmup_started = time.perf_counter()
        provider.warmup()
        warmup_seconds = time.perf_counter() - warmup_started
        first_started = time.perf_counter()
        first = provider.observe(
            image,
            sequence=0,
            prompts=("cup", "book", "phone"),
        )
        first_seconds = time.perf_counter() - first_started
        provider.reset()
        second_started = time.perf_counter()
        second = provider.observe(
            image,
            sequence=0,
            prompts=("cup", "book", "phone"),
        )
        second_seconds = time.perf_counter() - second_started
        return {
            "status": "passed",
            "scope": "supervised persistent worker lifecycle on synthetic 640x360 frames",
            "warmup_seconds": warmup_seconds,
            "first_frame_seconds": first_seconds,
            "post_reset_first_frame_seconds": second_seconds,
            "first_observation_count": len(first.observations),
            "post_reset_observation_count": len(second.observations),
            "worker_alive": bool(provider._process and provider._process.is_alive()),
            "wall_time_seconds": time.perf_counter() - started,
        }
    finally:
        provider.close()


def smoke_map_load() -> dict[str, object]:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    model_path = _registry().trusted_path("map-anything-apache")
    started = time.perf_counter()
    model = load_map_anything_local(
        model_path,
        device="cuda",
    )
    torch.cuda.synchronize()
    report = {
        "status": "passed",
        "scope": "MapAnything checkpoint load; no reconstruction claim",
        "wall_time_seconds": time.perf_counter() - started,
        "parameters": sum(parameter.numel() for parameter in model.parameters()),
        "dtype": str(next(model.parameters()).dtype),
        "cuda": _cuda_memory(torch),
    }
    del model
    gc.collect()
    torch.cuda.empty_cache()
    return report


def smoke_map_infer() -> dict[str, object]:
    import torch
    from mapanything.utils.image import load_images

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    model_path = _registry().trusted_path("map-anything-apache")
    started = time.perf_counter()
    model = load_map_anything_local(
        model_path,
        device="cuda",
    )
    with tempfile.TemporaryDirectory(prefix="worldstate-map-smoke-") as directory:
        root = Path(directory)
        first = _synthetic_frame()
        second = np.roll(first, shift=18, axis=1)
        paths = [root / "view-0.jpg", root / "view-1.jpg"]
        if not cv2.imwrite(str(paths[0]), first) or not cv2.imwrite(str(paths[1]), second):
            raise RuntimeError("could not create MapAnything smoke inputs")
        views = load_images(
            [str(path) for path in paths],
            resize_mode="fixed_size",
            size=(224, 224),
            verbose=False,
        )
        predictions = model.infer(
            views,
            memory_efficient_inference=True,
            minibatch_size=1,
            use_amp=True,
            amp_dtype="fp16",
            apply_mask=False,
            mask_edges=False,
            apply_confidence_mask=False,
        )
        torch.cuda.synchronize()
    report = {
        "status": "passed",
        "scope": "MapAnything two-view 224x224 synthetic reconstruction smoke",
        "wall_time_seconds": time.perf_counter() - started,
        "view_count": len(predictions),
        "output_keys": sorted({str(key) for prediction in predictions for key in prediction}),
        "cuda": _cuda_memory(torch),
    }
    del predictions
    del model
    gc.collect()
    torch.cuda.empty_cache()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "component",
        choices=("live", "live-benchmark", "supervised-worker", "map-load", "map-infer"),
    )
    parser.add_argument("--frames", type=int, default=24)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    if arguments.component == "live":
        report = smoke_live()
    elif arguments.component == "live-benchmark":
        report = benchmark_live(arguments.frames)
    elif arguments.component == "supervised-worker":
        report = smoke_supervised_worker()
    elif arguments.component == "map-load":
        report = smoke_map_load()
    else:
        report = smoke_map_infer()
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


if __name__ == "__main__":
    main()
