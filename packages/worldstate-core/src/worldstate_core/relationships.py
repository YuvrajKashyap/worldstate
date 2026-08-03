"""Spatial relationship inference for scene graphs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import sqrt

from worldstate_core.association import Vector3


class SpatialRelation(StrEnum):
    LEFT_OF = "left_of"
    RIGHT_OF = "right_of"
    ABOVE = "above"
    BELOW = "below"
    NEAR = "near"


@dataclass(frozen=True, slots=True)
class PositionedEntity:
    entity_id: str
    position_m: Vector3


@dataclass(frozen=True, slots=True)
class RelationshipCandidate:
    subject_entity_id: str
    object_entity_id: str
    relation: SpatialRelation
    confidence: float


def infer_pair_relationships(
    subject: PositionedEntity,
    object_: PositionedEntity,
    *,
    axis_margin_m: float = 0.08,
    near_distance_m: float = 0.75,
) -> tuple[RelationshipCandidate, ...]:
    """Infer conservative directional and proximity relations."""

    sx, sy, sz = subject.position_m
    ox, oy, oz = object_.position_m
    candidates: list[RelationshipCandidate] = []

    if abs(sx - ox) >= axis_margin_m:
        relation = SpatialRelation.LEFT_OF if sx < ox else SpatialRelation.RIGHT_OF
        confidence = min(1.0, 0.5 + abs(sx - ox) / max(near_distance_m, 0.01))
        candidates.append(
            RelationshipCandidate(subject.entity_id, object_.entity_id, relation, confidence)
        )
    if abs(sy - oy) >= axis_margin_m:
        relation = SpatialRelation.BELOW if sy < oy else SpatialRelation.ABOVE
        confidence = min(1.0, 0.5 + abs(sy - oy) / max(near_distance_m, 0.01))
        candidates.append(
            RelationshipCandidate(subject.entity_id, object_.entity_id, relation, confidence)
        )

    distance = sqrt((sx - ox) ** 2 + (sy - oy) ** 2 + (sz - oz) ** 2)
    if distance <= near_distance_m:
        confidence = max(0.0, 1.0 - distance / near_distance_m)
        candidates.append(
            RelationshipCandidate(
                subject.entity_id,
                object_.entity_id,
                SpatialRelation.NEAR,
                confidence,
            )
        )
    return tuple(candidates)
