"""Deterministic provider used for demos, tests, and frontend development."""

from __future__ import annotations

from math import sin
from time import perf_counter

import numpy as np

from worldstate_api.providers.base import ProviderObservation, ProviderResult


class ReplayPerceptionProvider:
    @property
    def provider_id(self) -> str:
        return "worldstate.replay.v1"

    def observe(
        self,
        image_bgr: np.ndarray,
        *,
        sequence: int,
        prompts: tuple[str, ...],
    ) -> ProviderResult:
        started = perf_counter()
        height, width = image_bgr.shape[:2]
        labels = prompts[:3] or ("cup", "book", "phone")
        observations: list[ProviderObservation] = []
        for index, label in enumerate(labels):
            phase = sequence * 0.012 + index * 1.9
            center_x = width * (0.25 + index * 0.22) + sin(phase) * width * 0.06
            center_y = height * (0.42 + index * 0.08) + sin(phase * 0.7) * height * 0.03
            box_width = max(32.0, width * (0.12 - index * 0.015))
            box_height = max(32.0, height * (0.22 - index * 0.02))
            observations.append(
                ProviderObservation(
                    label=label,
                    confidence=max(0.55, 0.94 - index * 0.08),
                    box_xyxy=(
                        max(0.0, center_x - box_width / 2),
                        max(0.0, center_y - box_height / 2),
                        min(float(width), center_x + box_width / 2),
                        min(float(height), center_y + box_height / 2),
                    ),
                    position_m=(
                        (center_x / width - 0.5) * 2.0,
                        (0.5 - center_y / height) * 1.2,
                        1.0 + index * 0.25,
                    ),
                    embedding=tuple(
                        1.0 if component == index else 0.05
                        for component in range(max(4, len(labels)))
                    ),
                )
            )
        return ProviderResult(
            observations=tuple(observations),
            inference_ms=(perf_counter() - started) * 1000.0,
            discovery_ran=sequence % 12 == 0,
            depth_ran=sequence % 4 == 0,
            embedding_ran=sequence % 12 == 0,
            diagnostics={"mode": "deterministic_replay"},
        )

    def close(self) -> None:
        return None
