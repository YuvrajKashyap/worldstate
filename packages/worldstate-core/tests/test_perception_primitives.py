from __future__ import annotations

from uuid import UUID

import pytest

from worldstate_core.association import (
    AssociationConfig,
    ObservationCandidate,
    TrackHypothesis,
    associate,
    box_iou,
    cosine_similarity,
    distance_m,
)
from worldstate_core.ids import uuid7
from worldstate_core.policy import PromptPolicyError, validate_object_prompts
from worldstate_core.relationships import (
    PositionedEntity,
    SpatialRelation,
    infer_pair_relationships,
)
from worldstate_core.uncertainty import UncertaintySignals, aggregate_uncertainty


def test_uuid7_is_valid_and_time_ordered() -> None:
    first = uuid7(1_700_000_000_000)
    second = uuid7(1_700_000_000_001)

    assert UUID(first).version == 7
    assert UUID(second).version == 7
    assert first < second


def test_uuid7_rejects_out_of_range_timestamp() -> None:
    with pytest.raises(ValueError, match="48 bits"):
        uuid7(1 << 48)


def test_prompt_policy_normalizes_and_deduplicates() -> None:
    assert validate_object_prompts(("  coffee   cup ", "book", "book")) == (
        "coffee cup",
        "book",
    )


@pytest.mark.parametrize(
    "prompts,message",
    [
        ((), "at least one"),
        (("",), "blank"),
        (("x" * 81,), "80"),
        (("infer ethnicity",), "sensitive-trait"),
        (("race classification",), "sensitive-trait"),
    ],
)
def test_prompt_policy_rejects_invalid_requests(
    prompts: tuple[str, ...],
    message: str,
) -> None:
    with pytest.raises(PromptPolicyError, match=message):
        validate_object_prompts(prompts)


def test_prompt_policy_honors_maximum() -> None:
    with pytest.raises(PromptPolicyError, match="no more than 1"):
        validate_object_prompts(("cup", "book"), maximum=1)


def test_association_primitives_handle_missing_and_degenerate_inputs() -> None:
    assert box_iou((0, 0, 2, 2), (1, 1, 3, 3)) == pytest.approx(1 / 7)
    assert box_iou((0, 0, 0, 0), (0, 0, 0, 0)) == 0.0
    assert cosine_similarity((1.0, 0.0), (1.0, 0.0)) == 1.0
    assert cosine_similarity((0.0, 0.0), (1.0, 0.0)) is None
    assert cosine_similarity(None, (1.0,)) is None
    assert distance_m((0, 0, 0), (3, 4, 0)) == 5.0
    assert distance_m(None, (0, 0, 0)) is None


def test_hungarian_association_returns_global_matches_and_unmatched_ids() -> None:
    tracks = (
        TrackHypothesis("cup-1", "cup", (0, 0, 10, 10), (0, 0, 1), (1, 0)),
        TrackHypothesis("book-1", "book", (20, 20, 30, 30), (1, 0, 1), (0, 1)),
    )
    observations = (
        ObservationCandidate("obs-book", "book", 0.95, (20, 20, 30, 30), (1, 0, 1), (0, 1)),
        ObservationCandidate("obs-cup", "cup", 0.95, (0, 0, 10, 10), (0, 0, 1), (1, 0)),
        ObservationCandidate("obs-far", "lamp", 0.9, (100, 100, 110, 110), (9, 9, 9), None),
    )

    result = associate(tracks, observations)

    assert {(item.entity_id, item.observation_id) for item in result.matches} == {
        ("cup-1", "obs-cup"),
        ("book-1", "obs-book"),
    }
    assert result.unmatched_entity_ids == ()
    assert result.unmatched_observation_ids == ("obs-far",)


def test_association_handles_empty_sides_and_strict_gates() -> None:
    track = TrackHypothesis("entity", "cup", (0, 0, 1, 1))
    observation = ObservationCandidate("observation", "cup", 0.9, (10, 10, 11, 11))

    empty = associate((track,), ())
    rejected = associate((track,), (observation,))

    assert empty.unmatched_entity_ids == ("entity",)
    assert rejected.matches == ()
    assert rejected.unmatched_observation_ids == ("observation",)


def test_association_preserves_identity_when_detector_confidence_dips() -> None:
    track = TrackHypothesis(
        "cup-1",
        "cup",
        (10, 10, 40, 50),
        (0.0, 0.0, 1.0),
        (1.0, 0.0),
    )
    observation = ObservationCandidate(
        "blurred-cup",
        "cup",
        0.18,
        (12, 11, 42, 51),
        (0.02, 0.0, 1.0),
        (0.99, 0.01),
    )

    result = associate((track,), (observation,))

    assert len(result.matches) == 1
    assert result.matches[0].entity_id == "cup-1"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"iou_weight": 0, "appearance_weight": 0, "position_weight": 0, "label_weight": 0},
        {"iou_weight": -1},
        {"minimum_iou": 1.1},
        {"maximum_distance_m": 0},
    ],
)
def test_association_config_rejects_invalid_values(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        AssociationConfig(**kwargs)


def test_relationship_inference_is_directional_and_bounded() -> None:
    left = PositionedEntity("left", (0.0, 1.0, 0.0))
    right = PositionedEntity("right", (0.5, 0.0, 0.0))

    relations = infer_pair_relationships(left, right)
    kinds = {item.relation for item in relations}

    assert SpatialRelation.LEFT_OF in kinds
    assert SpatialRelation.ABOVE in kinds
    assert all(0.0 <= item.confidence <= 1.0 for item in relations)


def test_uncertainty_aggregation_and_validation() -> None:
    signals = UncertaintySignals(1.0, 0.5, 0.0, 0.5, 1.0)
    assert aggregate_uncertainty(signals) == pytest.approx(0.575)
    with pytest.raises(ValueError, match="between 0 and 1"):
        UncertaintySignals(1.1, 0, 0, 0, 0)
