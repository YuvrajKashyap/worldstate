from datetime import UTC, datetime

import pytest

from worldstate_core.domain import (
    EntityLayer,
    EntityState,
    EventKind,
    PresenceState,
    SceneEntity,
    WorldEvent,
)

NOW = datetime(2026, 7, 30, tzinfo=UTC)


def test_scene_entity_requires_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SceneEntity(
            entity_id="entity-1",
            scene_id="scene-1",
            layer=EntityLayer.PERSISTENT,
            label="mug",
            created_at=datetime(2026, 7, 30),
        )


@pytest.mark.parametrize("field_name", ["entity_id", "scene_id", "label"])
def test_scene_entity_requires_identifiers_and_label(field_name: str) -> None:
    values = {
        "entity_id": "entity-1",
        "scene_id": "scene-1",
        "layer": EntityLayer.PERSISTENT,
        "label": "mug",
        "created_at": NOW,
    }
    values[field_name] = " "

    with pytest.raises(ValueError, match=f"{field_name} is required"):
        SceneEntity(**values)  # type: ignore[arg-type]


def test_entity_state_accepts_valid_evidence() -> None:
    state = EntityState(
        entity_id="entity-1",
        observed_at=NOW,
        presence=PresenceState.VISIBLE,
        confidence=0.91,
        position_m=(0.1, 0.2, 0.3),
        evidence_ids=("frame-4",),
    )

    assert state.position_m == (0.1, 0.2, 0.3)


def test_entity_state_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        EntityState(
            entity_id="entity-1",
            observed_at=NOW,
            presence=PresenceState.VISIBLE,
            confidence=1.01,
        )


def test_entity_state_rejects_blank_evidence() -> None:
    with pytest.raises(ValueError, match="cannot contain blank"):
        EntityState(
            entity_id="entity-1",
            observed_at=NOW,
            presence=PresenceState.VISIBLE,
            confidence=0.8,
            evidence_ids=(" ",),
        )


def test_world_event_requires_evidence() -> None:
    with pytest.raises(ValueError, match="at least one evidence"):
        WorldEvent(
            event_id="event-1",
            scene_id="scene-1",
            entity_id="entity-1",
            kind=EventKind.MOVED,
            occurred_at=NOW,
            confidence=0.8,
            evidence_ids=(),
        )


@pytest.mark.parametrize("field_name", ["event_id", "scene_id", "entity_id"])
def test_world_event_requires_identifiers(field_name: str) -> None:
    values = {
        "event_id": "event-1",
        "scene_id": "scene-1",
        "entity_id": "entity-1",
        "kind": EventKind.MOVED,
        "occurred_at": NOW,
        "confidence": 0.8,
        "evidence_ids": ("frame-1",),
    }
    values[field_name] = " "

    with pytest.raises(ValueError, match=f"{field_name} is required"):
        WorldEvent(**values)  # type: ignore[arg-type]


def test_world_event_rejects_blank_evidence() -> None:
    with pytest.raises(ValueError, match="cannot contain blank"):
        WorldEvent(
            event_id="event-1",
            scene_id="scene-1",
            entity_id="entity-1",
            kind=EventKind.MOVED,
            occurred_at=NOW,
            confidence=0.8,
            evidence_ids=(" ",),
        )
