"""Framework-independent domain primitives for WorldState."""

from worldstate_core.domain import (
    EntityLayer,
    EntityState,
    EventKind,
    PresenceState,
    SceneEntity,
    WorldEvent,
)
from worldstate_core.state import decay_confidence, next_presence_state

__all__ = [
    "EntityLayer",
    "EntityState",
    "EventKind",
    "PresenceState",
    "SceneEntity",
    "WorldEvent",
    "decay_confidence",
    "next_presence_state",
]
