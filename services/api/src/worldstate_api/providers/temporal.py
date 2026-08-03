"""Bounded temporal confirmation for learned webcam observations."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from worldstate_api.providers.base import ProviderObservation, ProviderResult


@dataclass(slots=True)
class _Hypothesis:
    label: str
    box_xyxy: tuple[float, float, float, float]
    hits: int
    discovery_hits: int
    confidence_sum: float
    promoted: bool = False
    missed: int = 0


class TemporalObservationFilter:
    """Require stable evidence before an observation can enter world memory.

    High-confidence observations need three consecutive frames. Lower-confidence
    observations additionally need two independent detector passes, so a single
    Grounding DINO proposal cannot become durable merely because optical flow
    propagates it.
    """

    def __init__(
        self,
        *,
        high_confidence: float = 0.65,
        minimum_average_confidence: float = 0.28,
        minimum_hits: int = 3,
        maximum_missed: int = 90,
        maximum_hypotheses: int = 64,
    ) -> None:
        self.high_confidence = high_confidence
        self.minimum_average_confidence = minimum_average_confidence
        self.minimum_hits = minimum_hits
        self.maximum_missed = maximum_missed
        self.maximum_hypotheses = maximum_hypotheses
        self._hypotheses: list[_Hypothesis] = []

    def reset(self) -> None:
        self._hypotheses.clear()

    def apply(self, result: ProviderResult, *, sequence: int) -> ProviderResult:
        del sequence  # Ordering is guaranteed by the WebSocket frame protocol.
        observations = self._suppress_duplicates(result.observations)
        unmatched_hypotheses = set(range(len(self._hypotheses)))
        emitted: list[ProviderObservation] = []
        promotions = 0

        for observation in observations:
            best_index: int | None = None
            best_score = 0.0
            for index in unmatched_hypotheses:
                hypothesis = self._hypotheses[index]
                if hypothesis.label != observation.label.casefold().strip():
                    continue
                score = self._match_score(hypothesis.box_xyxy, observation.box_xyxy)
                if score > best_score:
                    best_index = index
                    best_score = score

            if best_index is None or best_score < 0.20:
                if len(self._hypotheses) >= self.maximum_hypotheses:
                    continue
                hypothesis = _Hypothesis(
                    label=observation.label.casefold().strip(),
                    box_xyxy=observation.box_xyxy,
                    hits=1,
                    discovery_hits=1 if result.discovery_ran else 0,
                    confidence_sum=observation.confidence,
                )
                self._hypotheses.append(hypothesis)
            else:
                unmatched_hypotheses.remove(best_index)
                hypothesis = self._hypotheses[best_index]
                hypothesis.box_xyxy = observation.box_xyxy
                hypothesis.hits += 1
                hypothesis.discovery_hits += int(result.discovery_ran)
                hypothesis.confidence_sum += observation.confidence
                hypothesis.missed = 0

            average_confidence = hypothesis.confidence_sum / hypothesis.hits
            required_average_confidence = (
                max(0.42, self.minimum_average_confidence)
                if hypothesis.label == "unknown object"
                else self.minimum_average_confidence
            )
            confirmed = hypothesis.hits >= self.minimum_hits and (
                observation.confidence >= self.high_confidence
                or (
                    hypothesis.discovery_hits >= 2
                    and average_confidence >= required_average_confidence
                )
            )
            if confirmed and not hypothesis.promoted:
                hypothesis.promoted = True
                promotions += 1
            if hypothesis.promoted and observation.confidence >= 0.25:
                emitted.append(observation)

        for index in unmatched_hypotheses:
            self._hypotheses[index].missed += 1
        self._hypotheses = [item for item in self._hypotheses if item.missed <= self.maximum_missed]

        diagnostics = dict(result.diagnostics)
        diagnostics.update(
            {
                "temporal_pending": sum(not item.promoted for item in self._hypotheses),
                "temporal_promotions": promotions,
                "temporal_confirmed": len(emitted),
            }
        )
        return ProviderResult(
            observations=tuple(emitted),
            inference_ms=result.inference_ms,
            # A promotion must be durably checkpointed before ephemeral display
            # updates can safely refer to it.
            discovery_ran=result.discovery_ran or promotions > 0,
            depth_ran=result.depth_ran,
            embedding_ran=result.embedding_ran,
            diagnostics=diagnostics,
        )

    @classmethod
    def _suppress_duplicates(
        cls,
        observations: tuple[ProviderObservation, ...],
    ) -> tuple[ProviderObservation, ...]:
        kept: list[ProviderObservation] = []
        for observation in sorted(
            observations,
            key=lambda item: item.confidence,
            reverse=True,
        ):
            label = observation.label.casefold().strip()
            if any(
                (
                    label == other.label.casefold().strip()
                    and cls._iou(observation.box_xyxy, other.box_xyxy) >= 0.40
                )
                or cls._iou(observation.box_xyxy, other.box_xyxy) >= 0.75
                for other in kept
            ):
                continue
            kept.append(observation)
        return tuple(kept)

    @classmethod
    def _match_score(
        cls,
        left: tuple[float, float, float, float],
        right: tuple[float, float, float, float],
    ) -> float:
        overlap = cls._iou(left, right)
        if overlap > 0.0:
            return overlap
        left_center = ((left[0] + left[2]) / 2, (left[1] + left[3]) / 2)
        right_center = ((right[0] + right[2]) / 2, (right[1] + right[3]) / 2)
        distance = hypot(
            left_center[0] - right_center[0],
            left_center[1] - right_center[1],
        )
        diagonal = max(
            1.0,
            hypot(left[2] - left[0], left[3] - left[1]),
            hypot(right[2] - right[0], right[3] - right[1]),
        )
        return max(0.0, 0.40 * (1.0 - distance / diagonal))

    @staticmethod
    def _iou(
        left: tuple[float, float, float, float],
        right: tuple[float, float, float, float],
    ) -> float:
        intersection_width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
        intersection_height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
        intersection = intersection_width * intersection_height
        left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
        right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
        union = left_area + right_area - intersection
        return 0.0 if union <= 0.0 else intersection / union
