"""Calibratable uncertainty aggregation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UncertaintySignals:
    detector_uncertainty: float
    mask_instability: float
    association_ambiguity: float
    geometry_uncertainty: float
    staleness: float

    def __post_init__(self) -> None:
        for value in (
            self.detector_uncertainty,
            self.mask_instability,
            self.association_ambiguity,
            self.geometry_uncertainty,
            self.staleness,
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError("uncertainty signals must be between 0 and 1")


def aggregate_uncertainty(signals: UncertaintySignals) -> float:
    """Return a bounded baseline score pending held-out calibration."""

    weighted = (
        0.30 * signals.detector_uncertainty
        + 0.20 * signals.mask_instability
        + 0.25 * signals.association_ambiguity
        + 0.15 * signals.geometry_uncertainty
        + 0.10 * signals.staleness
    )
    return min(1.0, max(0.0, weighted))
