"""Core WorldState entities.

Observations describe what a provider returned. Entity state describes the
system's current belief. Keeping those concepts separate prevents a model score
from silently becoming permanent world state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class EntityLayer(StrEnum):
    """Durability class for an entity in the world model."""

    STATIC = "static"
    PERSISTENT = "persistent"
    TRANSIENT = "transient"


class PresenceState(StrEnum):
    """Explicit presence lifecycle for persistent objects."""

    VISIBLE = "visible"
    OCCLUDED = "occluded"
    PREDICTED = "predicted"
    MISSING = "missing"
    REDISCOVERED = "rediscovered"
    ARCHIVED = "archived"


class EventKind(StrEnum):
    """World changes that can be represented in the event timeline."""

    ADDED = "added"
    MOVED = "moved"
    ROTATED = "rotated"
    REMOVED = "removed"
    OCCLUDED = "occluded"
    REDISCOVERED = "rediscovered"


def _require_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_confidence(value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class SceneEntity:
    """A stable entity hypothesis in one scene."""

    entity_id: str
    scene_id: str
    layer: EntityLayer
    label: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.entity_id.strip():
            raise ValueError("entity_id is required")
        if not self.scene_id.strip():
            raise ValueError("scene_id is required")
        if not self.label.strip():
            raise ValueError("label is required")
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class EntityState:
    """A time-indexed belief about an entity."""

    entity_id: str
    observed_at: datetime
    presence: PresenceState
    confidence: float
    position_m: tuple[float, float, float] | None = None
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.entity_id.strip():
            raise ValueError("entity_id is required")
        _require_utc(self.observed_at, "observed_at")
        _require_confidence(self.confidence)
        if any(not evidence_id.strip() for evidence_id in self.evidence_ids):
            raise ValueError("evidence_ids cannot contain blank values")


@dataclass(frozen=True, slots=True)
class WorldEvent:
    """An evidence-backed change in entity state."""

    event_id: str
    scene_id: str
    entity_id: str
    kind: EventKind
    occurred_at: datetime
    confidence: float
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id is required")
        if not self.scene_id.strip():
            raise ValueError("scene_id is required")
        if not self.entity_id.strip():
            raise ValueError("entity_id is required")
        _require_utc(self.occurred_at, "occurred_at")
        _require_confidence(self.confidence)
        if not self.evidence_ids:
            raise ValueError("events require at least one evidence reference")
        if any(not evidence_id.strip() for evidence_id in self.evidence_ids):
            raise ValueError("evidence_ids cannot contain blank values")


def utc_now() -> datetime:
    """Return an aware timestamp behind a small testable boundary."""

    return datetime.now(UTC)
