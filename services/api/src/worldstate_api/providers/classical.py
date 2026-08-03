"""Weight-free OpenCV fallback for a genuinely usable local live path."""

from __future__ import annotations

from time import perf_counter

import cv2
import numpy as np

from worldstate_api.providers.base import ProviderObservation, ProviderResult


class ClassicalMotionProvider:
    """Detect moving foreground regions when learned models are unavailable."""

    def __init__(self, *, minimum_area_ratio: float = 0.0025) -> None:
        self.minimum_area_ratio = minimum_area_ratio
        self._background = cv2.createBackgroundSubtractorMOG2(
            history=300,
            varThreshold=24,
            detectShadows=True,
        )

    @property
    def provider_id(self) -> str:
        return "worldstate.opencv-motion.v1"

    def observe(
        self,
        image_bgr: np.ndarray,
        *,
        sequence: int,
        prompts: tuple[str, ...],
    ) -> ProviderResult:
        started = perf_counter()
        height, width = image_bgr.shape[:2]
        foreground = self._background.apply(image_bgr)
        _, foreground = cv2.threshold(foreground, 200, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel)
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(
            foreground,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        minimum_area = width * height * self.minimum_area_ratio
        observations: list[ProviderObservation] = []
        label = prompts[0] if len(prompts) == 1 else "moving object"
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
            area = float(cv2.contourArea(contour))
            if area < minimum_area:
                continue
            x, y, box_width, box_height = cv2.boundingRect(contour)
            crop = image_bgr[y : y + box_height, x : x + box_width]
            mean_bgr = cv2.mean(crop)[:3]
            embedding = tuple(float(value / 255.0) for value in mean_bgr)
            confidence = min(0.88, 0.45 + area / (width * height))
            observations.append(
                ProviderObservation(
                    label=label,
                    confidence=confidence,
                    box_xyxy=(float(x), float(y), float(x + box_width), float(y + box_height)),
                    embedding=embedding,
                )
            )
        return ProviderResult(
            observations=tuple(observations),
            inference_ms=(perf_counter() - started) * 1000.0,
            discovery_ran=True,
            depth_ran=False,
            embedding_ran=bool(observations),
            diagnostics={"foreground_regions": len(observations)},
        )

    def close(self) -> None:
        return None
