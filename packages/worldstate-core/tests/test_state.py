import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from worldstate_core.domain import PresenceState
from worldstate_core.state import decay_confidence, next_presence_state


def test_confidence_halves_after_one_half_life() -> None:
    assert decay_confidence(0.8, 30.0, 30.0) == pytest.approx(0.4)


@pytest.mark.parametrize(
    ("initial", "elapsed", "half_life", "message"),
    [
        (float("nan"), 0.0, 1.0, "finite"),
        (1.1, 0.0, 1.0, "between 0 and 1"),
        (0.8, -1.0, 1.0, "cannot be negative"),
        (0.8, 1.0, 0.0, "must be positive"),
    ],
)
def test_confidence_decay_rejects_invalid_inputs(
    initial: float,
    elapsed: float,
    half_life: float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        decay_confidence(initial, elapsed, half_life)


@given(
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    elapsed=st.floats(min_value=0.0, max_value=86_400.0, allow_nan=False),
    half_life=st.floats(min_value=0.01, max_value=86_400.0, allow_nan=False),
)
def test_confidence_decay_is_bounded(
    confidence: float,
    elapsed: float,
    half_life: float,
) -> None:
    result = decay_confidence(confidence, elapsed, half_life)

    assert math.isfinite(result)
    assert 0.0 <= result <= confidence


def test_missing_object_becomes_rediscovered_when_observed() -> None:
    state = next_presence_state(
        PresenceState.MISSING,
        directly_observed=True,
        occluded=False,
        confidence=0.9,
        missing_threshold=0.3,
    )

    assert state is PresenceState.REDISCOVERED


def test_archived_object_does_not_reactivate() -> None:
    state = next_presence_state(
        PresenceState.ARCHIVED,
        directly_observed=True,
        occluded=False,
        confidence=1.0,
        missing_threshold=0.3,
    )

    assert state is PresenceState.ARCHIVED


@pytest.mark.parametrize(
    ("directly_observed", "occluded", "confidence", "expected"),
    [
        (True, False, 0.9, PresenceState.VISIBLE),
        (False, True, 0.8, PresenceState.OCCLUDED),
        (False, False, 0.8, PresenceState.PREDICTED),
        (False, False, 0.2, PresenceState.MISSING),
    ],
)
def test_presence_transitions(
    directly_observed: bool,
    occluded: bool,
    confidence: float,
    expected: PresenceState,
) -> None:
    state = next_presence_state(
        PresenceState.VISIBLE,
        directly_observed=directly_observed,
        occluded=occluded,
        confidence=confidence,
        missing_threshold=0.3,
    )

    assert state is expected


@pytest.mark.parametrize(
    ("confidence", "threshold"),
    [(-0.1, 0.3), (1.1, 0.3), (0.8, -0.1), (0.8, 1.1)],
)
def test_presence_transition_rejects_invalid_probabilities(
    confidence: float,
    threshold: float,
) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        next_presence_state(
            PresenceState.VISIBLE,
            directly_observed=False,
            occluded=False,
            confidence=confidence,
            missing_threshold=threshold,
        )
