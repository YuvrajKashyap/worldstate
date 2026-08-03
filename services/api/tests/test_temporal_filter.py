from __future__ import annotations

from worldstate_api.providers.base import ProviderObservation, ProviderResult
from worldstate_api.providers.temporal import TemporalObservationFilter


def _result(
    *observations: ProviderObservation,
    discovery: bool = False,
) -> ProviderResult:
    return ProviderResult(
        observations=tuple(observations),
        inference_ms=5.0,
        discovery_ran=discovery,
        depth_ran=discovery,
        embedding_ran=discovery,
    )


def _observation(
    confidence: float = 0.48,
    box: tuple[float, float, float, float] = (10, 10, 60, 60),
) -> ProviderObservation:
    return ProviderObservation(
        label="cup",
        confidence=confidence,
        box_xyxy=box,
    )


def test_one_frame_low_confidence_detection_is_not_emitted() -> None:
    filter_ = TemporalObservationFilter()

    filtered = filter_.apply(_result(_observation(), discovery=True), sequence=1)

    assert filtered.observations == ()
    assert filtered.diagnostics["temporal_pending"] == 1


def test_stable_high_confidence_detection_requires_multiple_frames() -> None:
    filter_ = TemporalObservationFilter()

    assert filter_.apply(_result(_observation(0.72), discovery=True), sequence=1).observations == ()
    assert filter_.apply(_result(_observation(0.70)), sequence=2).observations == ()
    accepted = filter_.apply(_result(_observation(0.69)), sequence=3)

    assert len(accepted.observations) == 1
    assert accepted.diagnostics["temporal_promotions"] == 1


def test_low_confidence_track_requires_two_independent_discoveries() -> None:
    filter_ = TemporalObservationFilter()

    filter_.apply(_result(_observation(0.48), discovery=True), sequence=1)
    filter_.apply(_result(_observation(0.47)), sequence=2)
    still_pending = filter_.apply(_result(_observation(0.46)), sequence=3)
    accepted = filter_.apply(_result(_observation(0.50), discovery=True), sequence=4)

    assert still_pending.observations == ()
    assert len(accepted.observations) == 1


def test_small_known_item_can_confirm_at_lower_stable_confidence() -> None:
    filter_ = TemporalObservationFilter()

    filter_.apply(_result(_observation(0.34), discovery=True), sequence=1)
    filter_.apply(_result(_observation(0.33)), sequence=2)
    accepted = filter_.apply(
        _result(_observation(0.35), discovery=True),
        sequence=3,
    )

    assert len(accepted.observations) == 1


def test_unknown_object_keeps_stricter_low_confidence_confirmation() -> None:
    filter_ = TemporalObservationFilter()
    observation = ProviderObservation(
        label="unknown object",
        confidence=0.34,
        box_xyxy=(10, 10, 60, 60),
    )

    filter_.apply(_result(observation, discovery=True), sequence=1)
    filter_.apply(_result(observation), sequence=2)
    pending = filter_.apply(_result(observation, discovery=True), sequence=3)

    assert pending.observations == ()


def test_overlapping_duplicates_are_suppressed_before_confirmation() -> None:
    filter_ = TemporalObservationFilter()
    duplicate = ProviderObservation(
        label="cup",
        confidence=0.66,
        box_xyxy=(12, 11, 59, 61),
    )

    for sequence in range(1, 4):
        accepted = filter_.apply(
            _result(_observation(0.72), duplicate, discovery=sequence == 1),
            sequence=sequence,
        )

    assert len(accepted.observations) == 1


def test_confirmed_identity_survives_the_gap_between_discovery_passes() -> None:
    filter_ = TemporalObservationFilter()
    for sequence in range(1, 4):
        accepted = filter_.apply(
            _result(_observation(0.72), discovery=sequence == 1),
            sequence=sequence,
        )
    assert len(accepted.observations) == 1

    for sequence in range(4, 50):
        assert filter_.apply(_result(), sequence=sequence).observations == ()

    rediscovered = filter_.apply(
        _result(_observation(0.50), discovery=True),
        sequence=50,
    )
    assert len(rediscovered.observations) == 1
    assert rediscovered.diagnostics["temporal_promotions"] == 0
