"""Pure belief-state transition helpers."""

from __future__ import annotations

from math import isfinite

from worldstate_core.domain import PresenceState


def decay_confidence(
    initial_confidence: float,
    elapsed_seconds: float,
    half_life_seconds: float,
) -> float:
    """Exponentially decay confidence while evidence is absent."""

    values = (initial_confidence, elapsed_seconds, half_life_seconds)
    if not all(isfinite(value) for value in values):
        raise ValueError("confidence decay inputs must be finite")
    if not 0.0 <= initial_confidence <= 1.0:
        raise ValueError("initial_confidence must be between 0 and 1")
    if elapsed_seconds < 0.0:
        raise ValueError("elapsed_seconds cannot be negative")
    if half_life_seconds <= 0.0:
        raise ValueError("half_life_seconds must be positive")

    return initial_confidence * (0.5 ** (elapsed_seconds / half_life_seconds))


def next_presence_state(
    current: PresenceState,
    *,
    directly_observed: bool,
    occluded: bool,
    confidence: float,
    missing_threshold: float,
) -> PresenceState:
    """Apply the minimum deterministic presence lifecycle.

    Provider-specific association remains outside this function. This helper
    makes the distinction between observed, occluded, predicted, and missing
    explicit and testable.
    """

    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if not 0.0 <= missing_threshold <= 1.0:
        raise ValueError("missing_threshold must be between 0 and 1")
    if current is PresenceState.ARCHIVED:
        return PresenceState.ARCHIVED
    if directly_observed:
        if current in {PresenceState.MISSING, PresenceState.PREDICTED}:
            return PresenceState.REDISCOVERED
        return PresenceState.VISIBLE
    if occluded:
        return PresenceState.OCCLUDED
    if confidence < missing_threshold:
        return PresenceState.MISSING
    return PresenceState.PREDICTED
