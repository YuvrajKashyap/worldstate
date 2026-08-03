# pyright: basic, reportMissingImports=false, reportMissingTypeStubs=false
"""Lazy local adapters for the default learned perception stack.

This module is excluded from CPU-only coverage. It never downloads code or
weights at runtime; every model path must first pass ``ModelRegistry`` checks.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from time import perf_counter
from typing import Any, cast

import cv2
import numpy as np
from PIL import Image

from worldstate_api.providers.base import ProviderObservation, ProviderResult
from worldstate_api.providers.registry import ModelRegistry

_DISCOVERY_PROMPTS_PER_PASS = 16
_DISCOVERY_PROMPT_BATCH_SIZE = 12
LOGGER = logging.getLogger("worldstate.api.models")


@dataclass(frozen=True, slots=True)
class _DiscoveryResult:
    generation: int
    observations: tuple[ProviderObservation, ...]
    gray: np.ndarray
    sequence: int
    inference_ms: float


class ModelBundleProvider:
    """Grounding DINO discovery with DINOv2 and Depth Anything enrichment."""

    def __init__(
        self,
        registry: ModelRegistry,
        *,
        discovery_interval: int = 90,
        maintenance_discovery_interval: int = 300,
        mask_refresh_interval: int = 0,
        device: str = "cuda",
        background_discovery: bool = True,
    ) -> None:
        self.registry = registry
        self.discovery_interval = discovery_interval
        self.maintenance_discovery_interval = max(
            discovery_interval,
            maintenance_discovery_interval,
        )
        self.mask_refresh_interval = mask_refresh_interval
        self.device = device
        # Discovery is deliberately kept off the tracking/result critical path.
        # The learned models own the GPU while this one bounded worker runs;
        # optical-flow tracking remains CPU-only and continues to emit results.
        self.background_discovery = background_discovery
        self._loaded = False
        self._cached: tuple[ProviderObservation, ...] = ()
        self._torch: Any = None
        self._detector_processor: Any = None
        self._detector: Any = None
        self._embedding_processor: Any = None
        self._embedder: Any = None
        self._depth_processor: Any = None
        self._depth: Any = None
        self._previous_gray: np.ndarray | None = None
        self._processed_frames = 0
        self._last_discovery_sequence: int | None = None
        self._lost_tracks_since_sequence: int | None = None
        self._loss_discovery_attempts = 0
        self._discovery_prompt_batch_index = 0
        self._discovery_lock = threading.Lock()
        self._discovery_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="worldstate-discovery",
        )
        self._discovery_future: Future[_DiscoveryResult | None] | None = None
        self._discovery_generation = 0
        self._last_background_inference_ms = 0.0

    @property
    def provider_id(self) -> str:
        return "worldstate.default-model-bundle.v1"

    def warmup(self) -> None:
        """Verify and load the model bundle without scanning synthetic content.

        The first real discovery is asynchronous, so readiness must not depend
        on a generic-object pass over a throwaway image. That pass can generate
        an unbounded proposal set on synthetic pixels and delays startup without
        improving the first real result.
        """
        self._load()
        self.reset()

    def reset(self) -> None:
        """Discard temporal state while retaining the expensive model bundle."""

        self._finish_background_discovery()
        self._cached = ()
        self._previous_gray = None
        self._processed_frames = 0
        self._last_discovery_sequence = None
        self._lost_tracks_since_sequence = None
        self._loss_discovery_attempts = 0
        self._discovery_prompt_batch_index = 0
        with self._discovery_lock:
            self._discovery_generation += 1
            self._last_background_inference_ms = 0.0

    def _load(self) -> None:
        if self._loaded:
            return
        try:
            import torch
            from transformers import (
                AutoImageProcessor,
                AutoModel,
                AutoModelForDepthEstimation,
                GroundingDinoForObjectDetection,
                GroundingDinoProcessor,
            )
        except ImportError as error:
            raise RuntimeError(
                "The verified vision environment is not installed. "
                "Run `worldstate models install-defaults` inside WSL."
            ) from error

        grounding_path = self.registry.trusted_path("grounding-dino-tiny")
        LOGGER.info("Verified Grounding DINO model files")
        embedding_path = self.registry.trusted_path("dinov2-small")
        LOGGER.info("Verified DINOv2 model files")
        depth_path = self.registry.trusted_path("depth-anything-v2-small")
        LOGGER.info("Verified Depth Anything model files")

        self._torch = torch
        self._detector_processor = GroundingDinoProcessor.from_pretrained(
            grounding_path,
            local_files_only=True,
        )
        detector = GroundingDinoForObjectDetection.from_pretrained(
            grounding_path,
            local_files_only=True,
        )
        self._detector = cast(Any, detector).to(self.device)
        LOGGER.info("Loaded Grounding DINO on %s", self.device)
        self._embedding_processor = AutoImageProcessor.from_pretrained(
            embedding_path,
            local_files_only=True,
        )
        self._embedder = AutoModel.from_pretrained(
            embedding_path,
            local_files_only=True,
        ).to(self.device)
        LOGGER.info("Loaded DINOv2 on %s", self.device)
        self._depth_processor = AutoImageProcessor.from_pretrained(
            depth_path,
            local_files_only=True,
        )
        self._depth = AutoModelForDepthEstimation.from_pretrained(
            depth_path,
            local_files_only=True,
        ).to(self.device)
        LOGGER.info("Loaded Depth Anything on %s", self.device)
        for model in (self._detector, self._embedder, self._depth):
            model.eval()
        self._loaded = True

    def observe(
        self,
        image_bgr: np.ndarray,
        *,
        sequence: int,
        prompts: tuple[str, ...],
    ) -> ProviderResult:
        self._load()
        started = perf_counter()
        self._processed_frames += 1
        cadence_sequence = self._processed_frames
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        previous_gray = self._previous_gray
        motion_score = 0.0
        if previous_gray is not None and previous_gray.shape == gray.shape:
            motion_score = float(np.mean(cv2.absdiff(gray, previous_gray)) / 255.0)

        tracking_quality = 1.0
        had_tracks = bool(self._cached)
        if self._cached and previous_gray is not None:
            self._cached, tracking_quality = self._track_observations(
                previous_gray,
                gray,
                self._cached,
            )

        background_applied = self._apply_background_discovery(gray)
        if self._cached and self._loss_discovery_attempts == 0:
            self._lost_tracks_since_sequence = None
        elif had_tracks and self._lost_tracks_since_sequence is None:
            self._lost_tracks_since_sequence = cadence_sequence
        frames_since_discovery = (
            cadence_sequence - self._last_discovery_sequence
            if self._last_discovery_sequence is not None
            else self.discovery_interval
        )
        lost_tracks = (
            self._lost_tracks_since_sequence is not None
            and cadence_sequence - self._lost_tracks_since_sequence >= 3
        )
        scene_change = motion_score >= 0.08
        scheduled_discovery_interval = self._scheduled_discovery_interval(prompts)
        initial_discovery = not self._cached and self._last_discovery_sequence is None
        if initial_discovery and self.background_discovery:
            discovery = False
            self._start_background_discovery(
                image_bgr,
                gray,
                prompts,
                cadence_sequence,
            )
        elif initial_discovery:
            self._run_discovery(image_bgr, prompts, cadence_sequence)
            discovery = True
        elif frames_since_discovery >= scheduled_discovery_interval or lost_tracks:
            if self.background_discovery:
                discovery = False
                if self._start_background_discovery(
                    image_bgr,
                    gray,
                    prompts,
                    cadence_sequence,
                ):
                    self._lost_tracks_since_sequence = None
            else:
                self._run_discovery(image_bgr, prompts, cadence_sequence)
                discovery = True
        else:
            discovery = background_applied

        self._previous_gray = gray
        observations = self._cached
        gpu_allocated_bytes = int(self._torch.cuda.memory_allocated())
        gpu_reserved_bytes = int(self._torch.cuda.memory_reserved())
        return ProviderResult(
            observations=observations,
            inference_ms=(perf_counter() - started) * 1000.0,
            discovery_ran=discovery,
            depth_ran=discovery,
            embedding_ran=discovery,
            diagnostics={
                "model_bundle": self.provider_id,
                "source_sequence": sequence,
                "processed_frames": cadence_sequence,
                "motion_score": motion_score,
                "scene_change_trigger": int(scene_change),
                "tracking_quality": tracking_quality,
                "adaptive_discovery": int(discovery),
                "background_discovery": int(self._background_discovery_running()),
                "background_inference_ms": self._last_background_inference_ms,
                "mask_refresh": 0,
                "gpu_allocated_bytes": gpu_allocated_bytes,
                "gpu_reserved_bytes": gpu_reserved_bytes,
            },
        )

    def _run_discovery(
        self,
        image_bgr: np.ndarray,
        prompts: tuple[str, ...],
        sequence: int,
    ) -> None:
        previous = self._cached
        discovery_started = perf_counter()
        discovery_prompts = self._next_discovery_prompts(prompts)
        discovered = self._discover(image_bgr, discovery_prompts)
        if discovered:
            discovered = self._attach_depth(image_bgr, discovered)
        self._last_discovery_sequence = sequence
        if discovered:
            self._cached = self._merge_discovery(previous, discovered)
            self._lost_tracks_since_sequence = None
            self._loss_discovery_attempts = 0
        elif previous:
            # A focused vocabulary pass says nothing about categories assigned
            # to other passes. Successfully tracked visual evidence remains
            # authoritative even when this detector batch is empty.
            self._cached = previous
            self._loss_discovery_attempts = 0
            self._lost_tracks_since_sequence = None
        else:
            self._cached = ()
            self._lost_tracks_since_sequence = None
            self._loss_discovery_attempts = 0
        self._last_background_inference_ms = (perf_counter() - discovery_started) * 1000.0

    def _next_discovery_prompts(self, prompts: tuple[str, ...]) -> tuple[str, ...]:
        if len(prompts) <= _DISCOVERY_PROMPT_BATCH_SIZE:
            return prompts
        batch_count = (len(prompts) + _DISCOVERY_PROMPT_BATCH_SIZE - 1) // (
            _DISCOVERY_PROMPT_BATCH_SIZE
        )
        batch_index = self._discovery_prompt_batch_index % batch_count
        self._discovery_prompt_batch_index += 1
        start = batch_index * _DISCOVERY_PROMPT_BATCH_SIZE
        return prompts[start : start + _DISCOVERY_PROMPT_BATCH_SIZE]

    def _scheduled_discovery_interval(self, prompts: tuple[str, ...]) -> int:
        """Cover every vocabulary batch quickly, then enter maintenance cadence."""

        batch_count = max(
            1,
            (len(prompts) + _DISCOVERY_PROMPT_BATCH_SIZE - 1) // _DISCOVERY_PROMPT_BATCH_SIZE,
        )
        if self._discovery_prompt_batch_index < batch_count:
            return self.discovery_interval
        return self.maintenance_discovery_interval

    def _background_discovery_running(self) -> bool:
        with self._discovery_lock:
            future = self._discovery_future
            return future is not None and not future.done()

    def _start_background_discovery(
        self,
        image_bgr: np.ndarray,
        gray: np.ndarray,
        prompts: tuple[str, ...],
        sequence: int,
    ) -> bool:
        with self._discovery_lock:
            if self._discovery_future is not None and not self._discovery_future.done():
                return False
            generation = self._discovery_generation
            image_copy = image_bgr.copy()
            gray_copy = gray.copy()
            discovery_prompts = self._next_discovery_prompts(prompts)
            self._last_discovery_sequence = sequence

            def run() -> _DiscoveryResult | None:
                discovery_started = perf_counter()
                try:
                    observations = self._discover(
                        image_copy,
                        discovery_prompts,
                    )
                    if observations:
                        observations = self._attach_depth(image_copy, observations)
                    return _DiscoveryResult(
                        generation=generation,
                        observations=observations,
                        gray=gray_copy,
                        sequence=sequence,
                        inference_ms=(perf_counter() - discovery_started) * 1000.0,
                    )
                except Exception:
                    return None

            self._discovery_future = self._discovery_executor.submit(run)
            return True

    def _apply_background_discovery(self, current_gray: np.ndarray) -> bool:
        with self._discovery_lock:
            future = self._discovery_future
            if future is None or not future.done():
                return False
            self._discovery_future = None
        try:
            result = future.result()
        except Exception:
            return False
        if result is None or result.generation != self._discovery_generation:
            return False
        self._last_background_inference_ms = result.inference_ms
        aligned, _ = self._track_observations(
            result.gray,
            current_gray,
            result.observations,
        )
        # Each discovery pass covers only one rotating prompt batch. Preserve
        # still-tracked categories from the other batches instead of replacing
        # the complete scene with the newest partial scan.
        self._cached = self._merge_discovery(self._cached, aligned)
        return True

    def _finish_background_discovery(self) -> None:
        with self._discovery_lock:
            future = self._discovery_future
        if future is not None and not future.done():
            with suppress(Exception):
                future.result(timeout=15.0)
        with self._discovery_lock:
            if future is not None and future.done() and self._discovery_future is future:
                self._discovery_future = None

    @staticmethod
    def _track_observations(
        previous_gray: np.ndarray,
        current_gray: np.ndarray,
        observations: tuple[ProviderObservation, ...],
    ) -> tuple[tuple[ProviderObservation, ...], float]:
        """Propagate boxes with one batched forward/backward optical-flow pass.

        Feature selection remains scoped to each object so small desk items do
        not lose every corner to a textured monitor or keyboard. The expensive
        LK pyramid work, however, is shared by all selected corners in the
        frame. This preserves per-object validation while avoiding two full
        pyramid traversals for every tracked object.
        """

        if previous_gray.shape != current_gray.shape or not observations:
            return (), 0.0
        original_height, original_width = current_gray.shape[:2]
        tracking_scale = min(
            1.0,
            240.0 / original_width,
            135.0 / original_height,
        )
        if tracking_scale < 1.0:
            width = max(1, round(original_width * tracking_scale))
            height = max(1, round(original_height * tracking_scale))
            previous_gray = cv2.resize(
                previous_gray,
                (width, height),
                interpolation=cv2.INTER_AREA,
            )
            current_gray = cv2.resize(
                current_gray,
                (width, height),
                interpolation=cv2.INTER_AREA,
            )
        else:
            height, width = current_gray.shape[:2]
        prepared: list[
            tuple[
                ProviderObservation,
                tuple[float, float, float, float],
                int,
                int,
            ]
        ] = []
        point_batches: list[np.ndarray] = []
        point_offset = 0
        for observation in observations:
            x1, y1, x2, y2 = (coordinate * tracking_scale for coordinate in observation.box_xyxy)
            mask = np.zeros(previous_gray.shape, dtype=np.uint8)
            pad_x = max(4, int((x2 - x1) * 0.12))
            pad_y = max(4, int((y2 - y1) * 0.12))
            left = max(0, int(x1) - pad_x)
            top = max(0, int(y1) - pad_y)
            right = min(width, int(x2) + pad_x)
            bottom = min(height, int(y2) + pad_y)
            if right <= left or bottom <= top:
                continue
            mask[top:bottom, left:right] = 255
            points = cv2.goodFeaturesToTrack(
                previous_gray,
                maxCorners=20,
                qualityLevel=0.008,
                minDistance=4,
                mask=mask,
                blockSize=5,
            )
            point_count = 0 if points is None else len(points)
            if points is not None and point_count > 0:
                point_batches.append(points)
            prepared.append(
                (
                    observation,
                    (x1, y1, x2, y2),
                    point_offset,
                    point_offset + point_count,
                )
            )
            point_offset += point_count

        source_points: np.ndarray | None = None
        destination_points: np.ndarray | None = None
        valid_points: np.ndarray | None = None
        if point_batches:
            all_points = np.concatenate(point_batches, axis=0)
            next_points, status, _ = cv2.calcOpticalFlowPyrLK(
                previous_gray,
                current_gray,
                all_points,
                np.empty_like(all_points),
                winSize=(15, 15),
                maxLevel=2,
                criteria=(
                    cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                    16,
                    0.01,
                ),
            )
            if next_points is not None and status is not None:
                back_points, back_status, _ = cv2.calcOpticalFlowPyrLK(
                    current_gray,
                    previous_gray,
                    next_points,
                    np.empty_like(next_points),
                    winSize=(15, 15),
                    maxLevel=2,
                    criteria=(
                        cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                        16,
                        0.01,
                    ),
                )
                if back_points is not None and back_status is not None:
                    source_points = all_points.reshape(-1, 2)
                    destination_points = next_points.reshape(-1, 2)
                    backward_points = back_points.reshape(-1, 2)
                    valid_points = (
                        status.reshape(-1).astype(bool)
                        & back_status.reshape(-1).astype(bool)
                        & (np.linalg.norm(source_points - backward_points, axis=1) < 1.5)
                    )

        tracked: list[ProviderObservation] = []
        qualities: list[float] = []
        for observation, scaled_box, point_start, point_end in prepared:
            x1, y1, x2, y2 = scaled_box
            transformed_box: tuple[float, float, float, float] | None = None
            quality = 0.0
            if (
                point_end - point_start >= 4
                and source_points is not None
                and destination_points is not None
                and valid_points is not None
            ):
                object_valid = valid_points[point_start:point_end]
                source = source_points[point_start:point_end][object_valid]
                destination = destination_points[point_start:point_end][object_valid]
                if len(source) >= 4:
                    matrix, inliers = cv2.estimateAffinePartial2D(
                        source,
                        destination,
                        method=cv2.RANSAC,
                        ransacReprojThreshold=2.5,
                    )
                    if matrix is not None:
                        scale = float(np.hypot(matrix[0, 0], matrix[0, 1]))
                        if 0.72 <= scale <= 1.38:
                            corners = np.asarray(
                                [[[x1, y1], [x2, y1], [x2, y2], [x1, y2]]],
                                dtype=np.float32,
                            )
                            moved = cv2.transform(corners, matrix)[0]
                            transformed_box = (
                                float(np.min(moved[:, 0])),
                                float(np.min(moved[:, 1])),
                                float(np.max(moved[:, 0])),
                                float(np.max(moved[:, 1])),
                            )
                            inlier_fraction = (
                                float(np.mean(inliers)) if inliers is not None else 1.0
                            )
                            quality = min(1.0, len(source) / 10.0) * inlier_fraction

            if transformed_box is None:
                transformed_box, quality = ModelBundleProvider._template_track(
                    previous_gray,
                    current_gray,
                    (x1, y1, x2, y2),
                )
            if transformed_box is None:
                continue
            nx1, ny1, nx2, ny2 = transformed_box
            nx1 = max(0.0, min(float(width - 1), nx1))
            ny1 = max(0.0, min(float(height - 1), ny1))
            nx2 = max(nx1 + 1.0, min(float(width), nx2))
            ny2 = max(ny1 + 1.0, min(float(height), ny2))
            position = observation.position_m
            if position is not None:
                relative_depth = position[2]
                center_x = (nx1 + nx2) / 2.0
                position = (
                    (center_x / width - 0.5) * relative_depth,
                    (0.5 - ny2 / height) * relative_depth,
                    relative_depth,
                )
            # A validated tracker result is fresh visual evidence. Preserve a
            # promoted track while validation succeeds; removal is driven by
            # actual tracking/discovery loss rather than compounded per-frame
            # confidence shrinkage.
            confidence = max(
                0.26,
                observation.confidence * (0.999 if quality >= 0.45 else 0.985),
            )
            if confidence < 0.25:
                continue
            tracked.append(
                ProviderObservation(
                    label=observation.label,
                    confidence=confidence,
                    box_xyxy=(
                        nx1 / tracking_scale,
                        ny1 / tracking_scale,
                        nx2 / tracking_scale,
                        ny2 / tracking_scale,
                    ),
                    position_m=position,
                    bounds_m=observation.bounds_m,
                    embedding=observation.embedding,
                    # A segmentation mask belongs to the discovery frame. The
                    # box is propagated geometrically, but the bitmap is not;
                    # persisting it again would be stale evidence and would
                    # force needless artifact I/O on every tracking frame.
                    mask_png=None,
                    transient=observation.transient,
                )
            )
            qualities.append(quality)
        return tuple(tracked), float(np.mean(qualities)) if qualities else 0.0

    @staticmethod
    def _template_track(
        previous_gray: np.ndarray,
        current_gray: np.ndarray,
        box: tuple[float, float, float, float],
    ) -> tuple[tuple[float, float, float, float] | None, float]:
        height, width = current_gray.shape[:2]
        x1, y1, x2, y2 = box
        left = max(0, int(x1))
        top = max(0, int(y1))
        right = min(width, int(x2))
        bottom = min(height, int(y2))
        template = previous_gray[top:bottom, left:right]
        if template.size < 64 or float(np.std(template)) < 2.0:
            return None, 0.0
        margin_x = max(12, int((right - left) * 0.35))
        margin_y = max(12, int((bottom - top) * 0.35))
        search_left = max(0, left - margin_x)
        search_top = max(0, top - margin_y)
        search_right = min(width, right + margin_x)
        search_bottom = min(height, bottom + margin_y)
        search = current_gray[search_top:search_bottom, search_left:search_right]
        if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
            return None, 0.0
        response = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(response)
        if not np.isfinite(score) or score < 0.35:
            return None, 0.0
        moved_left = float(search_left + location[0])
        moved_top = float(search_top + location[1])
        return (
            moved_left,
            moved_top,
            moved_left + (right - left),
            moved_top + (bottom - top),
        ), float(max(0.0, min(1.0, score)))

    @staticmethod
    def _box_iou(
        left: list[float] | tuple[float, float, float, float],
        right: list[float] | tuple[float, float, float, float],
    ) -> float:
        left_x1, left_y1, left_x2, left_y2 = left
        right_x1, right_y1, right_x2, right_y2 = right
        width = max(0.0, min(left_x2, right_x2) - max(left_x1, right_x1))
        height = max(0.0, min(left_y2, right_y2) - max(left_y1, right_y1))
        intersection = width * height
        left_area = max(0.0, left_x2 - left_x1) * max(0.0, left_y2 - left_y1)
        right_area = max(0.0, right_x2 - right_x1) * max(0.0, right_y2 - right_y1)
        union = left_area + right_area - intersection
        return 0.0 if union <= 0.0 else intersection / union

    @classmethod
    def _merge_discovery(
        cls,
        tracked: tuple[ProviderObservation, ...],
        discovered: tuple[ProviderObservation, ...],
    ) -> tuple[ProviderObservation, ...]:
        """Refresh overlapping tracks without dropping independently tracked objects."""

        retained = [
            observation
            for observation in tracked
            if all(
                cls._box_iou(observation.box_xyxy, fresh.box_xyxy) < 0.55 for fresh in discovered
            )
        ]
        return (*discovered, *retained)

    @classmethod
    def _suppress_overlaps(
        cls,
        boxes: list[list[float]],
        scores: list[float],
        labels: list[str],
    ) -> tuple[list[list[float]], list[float], list[str]]:
        """Remove duplicate grounded boxes before SAM and DINOv2 enrichment."""

        kept: list[int] = []
        for index in sorted(
            range(len(scores)),
            key=lambda item: (
                labels[item].casefold().strip() != "unknown object",
                scores[item],
            ),
            reverse=True,
        ):
            label = labels[index].casefold().strip()
            duplicate = False
            for kept_index in kept:
                overlap = cls._box_iou(boxes[index], boxes[kept_index])
                same_label = label == labels[kept_index].casefold().strip()
                if (same_label and overlap >= 0.40) or overlap >= 0.75:
                    duplicate = True
                    break
            if not duplicate:
                kept.append(index)
        return (
            [boxes[index] for index in kept],
            [scores[index] for index in kept],
            [labels[index] for index in kept],
        )

    def _discover(
        self,
        image_bgr: np.ndarray,
        prompts: tuple[str, ...],
    ) -> tuple[ProviderObservation, ...]:
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(image_rgb)
        effective_prompts = list(prompts)
        if "object" not in {prompt.casefold().strip() for prompt in prompts}:
            effective_prompts.append("object")
        boxes: list[list[float]] = []
        scores: list[float] = []
        labels: list[str] = []
        target_sizes = self._torch.tensor([image.size[::-1]], device=self.device)
        for offset in range(0, len(effective_prompts), _DISCOVERY_PROMPTS_PER_PASS):
            prompt_batch = effective_prompts[offset : offset + _DISCOVERY_PROMPTS_PER_PASS]
            text = ". ".join(prompt_batch) + "."
            inputs = self._detector_processor(images=image, text=text, return_tensors="pt")
            inputs = {key: value.to(self.device) for key, value in inputs.items()}
            with (
                self._torch.inference_mode(),
                self._torch.autocast(
                    device_type="cuda",
                    dtype=self._torch.float16,
                ),
            ):
                outputs = self._detector(**inputs)
            processed = self._detector_processor.post_process_grounded_object_detection(
                outputs,
                inputs["input_ids"],
                threshold=0.25,
                text_threshold=0.20,
                target_sizes=target_sizes,
            )[0]
            boxes.extend(processed["boxes"].detach().cpu().tolist())
            scores.extend(processed["scores"].detach().cpu().tolist())
            labels.extend(
                self._canonical_discovery_label(str(label), prompt_batch)
                for label in processed["text_labels"]
            )
        boxes, scores, labels = self._suppress_overlaps(boxes, scores, labels)

        embeddings = self._embed_crops(image, boxes)
        observations: list[ProviderObservation] = []
        for box, score, label, embedding in zip(
            boxes,
            scores,
            labels,
            embeddings,
            strict=True,
        ):
            confidence = float(score)
            if confidence < 0.25:
                continue
            observations.append(
                ProviderObservation(
                    label=str(label),
                    confidence=confidence,
                    box_xyxy=cast(
                        tuple[float, float, float, float],
                        tuple(float(value) for value in box),
                    ),
                    embedding=embedding,
                    # Live presentation consumes boxes and relative bounds.
                    # Avoiding per-discovery SAM masks keeps open-vocabulary
                    # refreshes inside the real-time budget; depth uses the
                    # robust box median below.
                    mask_png=None,
                    transient=str(label).casefold().strip() == "person",
                )
            )
        return tuple(observations)

    @staticmethod
    def _canonical_discovery_label(raw_label: str, prompts: Sequence[str]) -> str:
        normalized = " ".join(raw_label.casefold().strip().split())
        if normalized == "object":
            return "unknown object"
        exact = next(
            (prompt for prompt in prompts if prompt.casefold().strip() == normalized),
            None,
        )
        if exact is not None:
            return exact
        matches = [prompt for prompt in prompts if prompt.casefold().strip() in normalized]
        if "earbuds" in matches:
            return "earbuds"
        if matches:
            return max(matches, key=lambda prompt: (len(prompt.split()), len(prompt)))
        return normalized or "unknown object"

    def _embed_crop(
        self,
        image: Image.Image,
        box: list[float],
    ) -> tuple[float, ...] | None:
        return self._embed_crops(image, [box])[0]

    def _embed_crops(
        self,
        image: Image.Image,
        boxes: Sequence[Sequence[float]],
    ) -> list[tuple[float, ...] | None]:
        results: list[tuple[float, ...] | None] = [None] * len(boxes)
        crops: list[Image.Image] = []
        indices: list[int] = []
        for index, box in enumerate(boxes):
            crop_box = cast(
                tuple[float, float, float, float],
                tuple(float(max(0.0, value)) for value in box),
            )
            crop = image.crop(crop_box)
            if crop.width == 0 or crop.height == 0:
                continue
            crops.append(crop)
            indices.append(index)
        if not crops:
            return results
        inputs = self._embedding_processor(images=crops, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with (
            self._torch.inference_mode(),
            self._torch.autocast(
                device_type="cuda",
                dtype=self._torch.float16,
            ),
        ):
            features = self._embedder(**inputs).last_hidden_state[:, 0]
            features = self._torch.nn.functional.normalize(features, dim=-1)
        vectors = features.float().cpu().tolist()
        for index, vector in zip(indices, vectors, strict=True):
            results[index] = tuple(float(value) for value in vector)
        return results

    def _attach_depth(
        self,
        image_bgr: np.ndarray,
        observations: tuple[ProviderObservation, ...],
    ) -> tuple[ProviderObservation, ...]:
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(image_rgb)
        inputs = self._depth_processor(images=image, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        with (
            self._torch.inference_mode(),
            self._torch.autocast(
                device_type="cuda",
                dtype=self._torch.float16,
            ),
        ):
            predicted_depth = self._depth(**inputs).predicted_depth
        depth = self._torch.nn.functional.interpolate(
            predicted_depth.unsqueeze(1),
            size=image_bgr.shape[:2],
            mode="bicubic",
            align_corners=False,
        ).squeeze()
        depth_array = depth.float().cpu().numpy()
        height, width = image_bgr.shape[:2]
        finite_depth = depth_array[np.isfinite(depth_array)]
        if finite_depth.size == 0:
            return observations
        near_inverse = float(np.percentile(finite_depth, 90))
        far_inverse = float(np.percentile(finite_depth, 10))
        inverse_span = max(1e-6, near_inverse - far_inverse)
        enriched: list[ProviderObservation] = []
        for observation in observations:
            x1, y1, x2, y2 = observation.box_xyxy
            left = int(max(0, min(width - 1, x1)))
            top = int(max(0, min(height - 1, y1)))
            right = int(max(left + 1, min(width, x2)))
            bottom = int(max(top + 1, min(height, y2)))
            cx = float((left + right) / 2)
            roi = depth_array[top:bottom, left:right]
            samples = roi[np.isfinite(roi)]
            if observation.mask_png is not None:
                decoded_mask = cv2.imdecode(
                    np.frombuffer(observation.mask_png, dtype=np.uint8),
                    cv2.IMREAD_GRAYSCALE,
                )
                if decoded_mask is not None and decoded_mask.shape == depth_array.shape:
                    object_samples = depth_array[(decoded_mask > 0) & np.isfinite(depth_array)]
                    if object_samples.size >= 16:
                        samples = object_samples
            inverse_depth = (
                float(np.median(samples))
                if samples.size > 0
                else float(depth_array[min(height - 1, bottom - 1), int(cx)])
            )
            # Depth Anything V2 provides relative inverse depth. Normalize it
            # into a stable camera-space interval where larger z means farther
            # from the webcam; this remains deliberately uncalibrated.
            closeness = float(np.clip((inverse_depth - far_inverse) / inverse_span, 0.0, 1.0))
            relative_depth = 1.85 - closeness * 1.1
            support_y = (0.5 - bottom / height) * relative_depth
            extent_x = max(0.02, (right - left) / width * relative_depth)
            extent_y = max(0.02, (bottom - top) / height * relative_depth)
            extent_z = max(0.02, min(extent_x, extent_y) * 0.35)
            position = (
                (cx / width - 0.5) * relative_depth,
                support_y,
                relative_depth,
            )
            enriched.append(
                ProviderObservation(
                    label=observation.label,
                    confidence=observation.confidence,
                    box_xyxy=observation.box_xyxy,
                    position_m=position,
                    bounds_m=(extent_x, extent_y, extent_z),
                    embedding=observation.embedding,
                    mask_png=observation.mask_png,
                    transient=observation.transient,
                )
            )
        return tuple(enriched)

    def close(self) -> None:
        self._finish_background_discovery()
        self._discovery_executor.shutdown(wait=True, cancel_futures=True)
        self._detector = None
        self._embedder = None
        self._depth = None
        if self._torch is not None and self._torch.cuda.is_available():
            self._torch.cuda.empty_cache()
