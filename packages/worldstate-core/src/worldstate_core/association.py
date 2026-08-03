# pyright: reportMissingTypeStubs=false, reportUnknownVariableType=false
"""Multimodal observation-to-entity association."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, sqrt
from typing import cast

import numpy as np
from scipy.optimize import linear_sum_assignment

type Vector3 = tuple[float, float, float]
type BoxXYXY = tuple[float, float, float, float]
type Embedding = tuple[float, ...]


@dataclass(frozen=True, slots=True)
class AssociationConfig:
    """Weights and gates for the assignment cost matrix."""

    iou_weight: float = 0.35
    appearance_weight: float = 0.25
    position_weight: float = 0.25
    label_weight: float = 0.15
    minimum_iou: float = 0.05
    minimum_cosine: float = 0.55
    maximum_distance_m: float = 1.25
    minimum_score: float = 0.35

    def __post_init__(self) -> None:
        weights = (
            self.iou_weight,
            self.appearance_weight,
            self.position_weight,
            self.label_weight,
        )
        if any(not isfinite(value) or value < 0.0 for value in weights):
            raise ValueError("association weights must be finite and non-negative")
        if sum(weights) <= 0.0:
            raise ValueError("at least one association weight must be positive")
        for value in (self.minimum_iou, self.minimum_cosine, self.minimum_score):
            if not 0.0 <= value <= 1.0:
                raise ValueError("association thresholds must be between 0 and 1")
        if self.maximum_distance_m <= 0.0:
            raise ValueError("maximum_distance_m must be positive")


@dataclass(frozen=True, slots=True)
class TrackHypothesis:
    entity_id: str
    label: str
    box_xyxy: BoxXYXY
    position_m: Vector3 | None = None
    embedding: Embedding | None = None


@dataclass(frozen=True, slots=True)
class ObservationCandidate:
    observation_id: str
    label: str
    confidence: float
    box_xyxy: BoxXYXY
    position_m: Vector3 | None = None
    embedding: Embedding | None = None


@dataclass(frozen=True, slots=True)
class AssociationMatch:
    entity_id: str
    observation_id: str
    score: float


@dataclass(frozen=True, slots=True)
class AssociationResult:
    matches: tuple[AssociationMatch, ...]
    unmatched_entity_ids: tuple[str, ...]
    unmatched_observation_ids: tuple[str, ...]


def box_iou(left: BoxXYXY, right: BoxXYXY) -> float:
    """Return intersection-over-union for two ``xyxy`` boxes."""

    left_x1, left_y1, left_x2, left_y2 = left
    right_x1, right_y1, right_x2, right_y2 = right
    intersection_width = max(0.0, min(left_x2, right_x2) - max(left_x1, right_x1))
    intersection_height = max(0.0, min(left_y2, right_y2) - max(left_y1, right_y1))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, left_x2 - left_x1) * max(0.0, left_y2 - left_y1)
    right_area = max(0.0, right_x2 - right_x1) * max(0.0, right_y2 - right_y1)
    union = left_area + right_area - intersection
    return 0.0 if union <= 0.0 else intersection / union


def cosine_similarity(left: Embedding | None, right: Embedding | None) -> float | None:
    if left is None or right is None or len(left) != len(right) or not left:
        return None
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return None
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def distance_m(left: Vector3 | None, right: Vector3 | None) -> float | None:
    if left is None or right is None:
        return None
    return sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _pair_score(
    track: TrackHypothesis,
    observation: ObservationCandidate,
    config: AssociationConfig,
) -> float | None:
    overlap = box_iou(track.box_xyxy, observation.box_xyxy)
    appearance = cosine_similarity(track.embedding, observation.embedding)
    distance = distance_m(track.position_m, observation.position_m)

    passes_gate = overlap >= config.minimum_iou
    passes_gate = passes_gate or (appearance is not None and appearance >= config.minimum_cosine)
    passes_gate = passes_gate or (distance is not None and distance <= config.maximum_distance_m)
    if not passes_gate:
        return None

    position_score = exp(-distance / config.maximum_distance_m) if distance is not None else 0.5
    appearance_score = (appearance + 1.0) / 2.0 if appearance is not None else 0.5
    label_score = 1.0 if track.label.casefold() == observation.label.casefold() else 0.15
    weighted = (
        config.iou_weight * overlap
        + config.appearance_weight * appearance_score
        + config.position_weight * position_score
        + config.label_weight * label_score
    )
    normalized = weighted / (
        config.iou_weight + config.appearance_weight + config.position_weight + config.label_weight
    )
    # Confidence controls belief in the observation, but it must not erase a
    # strong identity match. Detector confidence routinely dips during blur or
    # partial occlusion; multiplying the entire association score by it caused
    # otherwise identical tracks to fragment into new entity IDs.
    reliability = 0.70 + 0.30 * max(0.0, min(1.0, observation.confidence))
    return normalized * reliability


def associate(
    tracks: tuple[TrackHypothesis, ...],
    observations: tuple[ObservationCandidate, ...],
    config: AssociationConfig | None = None,
) -> AssociationResult:
    """Assign observations globally with Hungarian matching and explicit gates."""

    policy = config or AssociationConfig()
    if not tracks or not observations:
        return AssociationResult(
            matches=(),
            unmatched_entity_ids=tuple(track.entity_id for track in tracks),
            unmatched_observation_ids=tuple(item.observation_id for item in observations),
        )

    impossible = 1_000_000.0
    costs = np.full((len(tracks), len(observations)), impossible, dtype=np.float64)
    scores: dict[tuple[int, int], float] = {}
    for track_index, track in enumerate(tracks):
        for observation_index, observation in enumerate(observations):
            score = _pair_score(track, observation, policy)
            if score is not None and score >= policy.minimum_score:
                scores[(track_index, observation_index)] = score
                costs[track_index, observation_index] = 1.0 - score

    row_indices, column_indices = cast(
        tuple[np.ndarray, np.ndarray],
        linear_sum_assignment(costs),
    )
    matches: list[AssociationMatch] = []
    matched_tracks: set[int] = set()
    matched_observations: set[int] = set()
    for track_index, observation_index in zip(row_indices, column_indices, strict=True):
        score = scores.get((int(track_index), int(observation_index)))
        if score is None:
            continue
        matched_tracks.add(int(track_index))
        matched_observations.add(int(observation_index))
        matches.append(
            AssociationMatch(
                entity_id=tracks[int(track_index)].entity_id,
                observation_id=observations[int(observation_index)].observation_id,
                score=score,
            )
        )

    return AssociationResult(
        matches=tuple(matches),
        unmatched_entity_ids=tuple(
            track.entity_id for index, track in enumerate(tracks) if index not in matched_tracks
        ),
        unmatched_observation_ids=tuple(
            item.observation_id
            for index, item in enumerate(observations)
            if index not in matched_observations
        ),
    )
