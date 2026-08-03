"""Normalized provider contracts used by the coordinator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    label: str
    confidence: float
    box_xyxy: tuple[float, float, float, float]
    position_m: tuple[float, float, float] | None = None
    bounds_m: tuple[float, float, float] | None = None
    embedding: tuple[float, ...] | None = None
    mask_png: bytes | None = None
    transient: bool = False


@dataclass(frozen=True, slots=True)
class ProviderResult:
    observations: tuple[ProviderObservation, ...]
    inference_ms: float
    discovery_ran: bool
    depth_ran: bool
    embedding_ran: bool
    diagnostics: dict[str, float | int | str] = field(
        default_factory=lambda: dict[str, float | int | str]()
    )


@runtime_checkable
class LivePerceptionProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def observe(
        self,
        image_bgr: np.ndarray,
        *,
        sequence: int,
        prompts: tuple[str, ...],
    ) -> ProviderResult: ...

    def close(self) -> None: ...
