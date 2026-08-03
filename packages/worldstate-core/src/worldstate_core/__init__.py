"""Framework-independent domain primitives for WorldState."""

from worldstate_core.association import (
    AssociationConfig,
    AssociationMatch,
    AssociationResult,
    ObservationCandidate,
    TrackHypothesis,
    associate,
)
from worldstate_core.domain import (
    EntityLayer,
    EntityState,
    EventKind,
    PresenceState,
    SceneEntity,
    WorldEvent,
)
from worldstate_core.ids import uuid7
from worldstate_core.policy import PromptPolicyError, validate_object_prompts
from worldstate_core.relationships import SpatialRelation
from worldstate_core.state import decay_confidence, next_presence_state
from worldstate_core.uncertainty import UncertaintySignals, aggregate_uncertainty

__all__ = [
    "AssociationConfig",
    "AssociationMatch",
    "AssociationResult",
    "EntityLayer",
    "EntityState",
    "EventKind",
    "ObservationCandidate",
    "PresenceState",
    "PromptPolicyError",
    "SceneEntity",
    "SpatialRelation",
    "TrackHypothesis",
    "UncertaintySignals",
    "WorldEvent",
    "aggregate_uncertainty",
    "associate",
    "decay_confidence",
    "next_presence_state",
    "uuid7",
    "validate_object_prompts",
]
