"""Provider contracts owned by the WorldState domain."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class FrameReference:
    """A frame passed to a provider without prescribing an image library."""

    frame_id: str
    captured_at: datetime
    artifact_id: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class PerceptionInstance:
    """Normalized object observation returned by a perception provider."""

    observation_id: str
    label: str
    score: float
    box_xyxy: tuple[float, float, float, float]
    mask_artifact_id: str | None = None
    embedding_artifact_id: str | None = None


@dataclass(frozen=True, slots=True)
class GeometryResult:
    """Normalized geometry artifact references for a scan."""

    coordinate_frame: str
    point_cloud_artifact_id: str
    camera_artifact_id: str
    confidence_artifact_id: str | None = None
    approximate_scale: bool = True


@runtime_checkable
class PerceptionProvider(Protocol):
    """Object perception boundary."""

    @property
    def provider_id(self) -> str: ...

    async def observe(self, frame: FrameReference) -> Sequence[PerceptionInstance]: ...


@runtime_checkable
class GeometryProvider(Protocol):
    """Multi-view geometry boundary."""

    @property
    def provider_id(self) -> str: ...

    async def reconstruct(self, frames: Sequence[FrameReference]) -> GeometryResult: ...
