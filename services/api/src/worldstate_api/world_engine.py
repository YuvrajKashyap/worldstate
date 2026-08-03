"""Observation association and temporal world-state updates."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from math import sqrt
from typing import cast

from worldstate_api.artifacts import ArtifactStore
from worldstate_api.persistence import (
    EntityModel,
    EntityStateModel,
    SceneModel,
    WorldEventModel,
    WorldRepository,
    ensure_utc,
)
from worldstate_api.providers.base import ProviderObservation, ProviderResult
from worldstate_core import (
    AssociationConfig,
    ObservationCandidate,
    PresenceState,
    TrackHypothesis,
    UncertaintySignals,
    aggregate_uncertainty,
    associate,
    decay_confidence,
    next_presence_state,
)
from worldstate_core.ids import uuid7
from worldstate_core.relationships import PositionedEntity, infer_pair_relationships


@dataclass(frozen=True, slots=True)
class WorldObject:
    entity: EntityModel
    state: EntityStateModel
    mask_artifact_id: str | None


@dataclass(frozen=True, slots=True)
class WorldFrameUpdate:
    objects: tuple[WorldObject, ...]
    events: tuple[WorldEventModel, ...]


class WorldEngine:
    """Apply normalized provider output to an evidence-backed scene timeline."""

    def __init__(
        self,
        *,
        repository: WorldRepository,
        artifact_store: ArtifactStore,
        association_config: AssociationConfig | None = None,
    ) -> None:
        self.repository = repository
        self.artifact_store = artifact_store
        self.association_config = association_config or AssociationConfig()
        self._embeddings: dict[str, tuple[float, ...]] = {}
        self._live_objects: dict[str, dict[str, WorldObject]] = {}
        # Live display state must never wait on SQLite or artifact I/O.  The
        # two locks deliberately separate the frame-critical cache from the
        # durable append-only history writer.
        self._live_lock = threading.Lock()
        self._persistence_lock = threading.Lock()

    def process_ephemeral(
        self,
        *,
        scene_id: str,
        captured_at: datetime,
        provider_result: ProviderResult,
    ) -> WorldFrameUpdate:
        """Update the display-critical live state without durable I/O.

        Durable frames are sampled separately. Discovery frames are always
        persisted, so ordinary ephemeral updates only need to associate known
        tracks and can preserve entity identity entirely in memory.
        """

        with self._live_lock:
            cache = self._live_objects.get(scene_id)
            if not cache:
                return WorldFrameUpdate(objects=(), events=())
            tracks: list[TrackHypothesis] = []
            for item in cache.values():
                box = item.state.box_xyxy
                if box is None:
                    continue
                tracks.append(
                    TrackHypothesis(
                        entity_id=item.entity.id,
                        label=item.entity.canonical_label,
                        box_xyxy=cast(
                            tuple[float, float, float, float],
                            tuple(float(value) for value in box),
                        ),
                        position_m=(
                            cast(
                                tuple[float, float, float],
                                tuple(float(value) for value in item.state.position_m),
                            )
                            if item.state.position_m is not None
                            else None
                        ),
                        embedding=self._embeddings.get(item.entity.id),
                    )
                )
            candidates = tuple(
                ObservationCandidate(
                    observation_id=f"ephemeral-{index}",
                    label=observation.label,
                    confidence=observation.confidence,
                    box_xyxy=observation.box_xyxy,
                    position_m=observation.position_m,
                    embedding=observation.embedding,
                )
                for index, observation in enumerate(provider_result.observations)
            )
            candidate_map = {candidate.observation_id: candidate for candidate in candidates}
            provider_map = {
                f"ephemeral-{index}": observation
                for index, observation in enumerate(provider_result.observations)
            }
            result = associate(tuple(tracks), candidates, self.association_config)
            output: list[WorldObject] = []
            for match in result.matches:
                previous = cache[match.entity_id]
                candidate = candidate_map[match.observation_id]
                presence = (
                    "rediscovered"
                    if previous.state.presence in {"missing", "occluded"}
                    else "visible"
                )
                provider_observation = provider_map[match.observation_id]
                uncertainty = aggregate_uncertainty(
                    UncertaintySignals(
                        detector_uncertainty=1.0 - candidate.confidence,
                        mask_instability=0.35,
                        association_ambiguity=1.0 - match.score,
                        geometry_uncertainty=0.2 if candidate.position_m is not None else 0.7,
                        staleness=0.0,
                    )
                )
                state = EntityStateModel(
                    id=uuid7(),
                    entity_id=previous.entity.id,
                    valid_from=captured_at,
                    valid_to=None,
                    presence=presence,
                    confidence=candidate.confidence,
                    uncertainty=uncertainty,
                    position_m=(
                        list(candidate.position_m) if candidate.position_m is not None else None
                    ),
                    quaternion_xyzw=None,
                    bounds_m=(
                        list(provider_observation.bounds_m)
                        if provider_observation.bounds_m is not None
                        else None
                    ),
                    box_xyxy=list(candidate.box_xyxy),
                    evidence_ids=[],
                )
                previous.entity.last_seen_at = captured_at
                previous.entity.status = presence
                item = WorldObject(previous.entity, state, None)
                cache[previous.entity.id] = item
                output.append(item)
                if candidate.embedding is not None:
                    self._embeddings[previous.entity.id] = candidate.embedding
            return WorldFrameUpdate(objects=tuple(output), events=())

    def process(
        self,
        *,
        scene_id: str,
        capture_session_id: str,
        sequence: int,
        captured_at: datetime,
        width: int,
        height: int,
        quality: dict[str, float],
        provider_result: ProviderResult,
    ) -> WorldFrameUpdate:
        with self._persistence_lock:
            scene_row = self.repository.get_scene(scene_id)
            if scene_row is None:
                raise KeyError(scene_id)
            scene, _ = scene_row
            with self._live_lock:
                embeddings = dict(self._embeddings)
            apply_frame = partial(
                self._process_locked,
                scene=scene,
                scene_id=scene_id,
                capture_session_id=capture_session_id,
                sequence=sequence,
                captured_at=captured_at,
                width=width,
                height=height,
                quality=quality,
                provider_result=provider_result,
                embeddings=embeddings,
            )
            # Artifact-backed discovery keeps the store's compensating-write
            # path. Ordinary tracking frames are one atomic transaction,
            # avoiding a commit/fsync per observation, state, event, and
            # relationship while retaining artifact failure semantics.
            has_artifacts = scene.persistence_enabled and any(
                observation.mask_png is not None for observation in provider_result.observations
            )
            if has_artifacts:
                update = apply_frame()
            else:
                with self.repository.database.transaction():
                    update = apply_frame()

            # Merge the durable result without replacing a newer ephemeral
            # state produced while the checkpoint was on disk.
            with self._live_lock:
                self._embeddings.update(embeddings)
                cache = self._live_objects.setdefault(scene_id, {})
                for item in update.objects:
                    current = cache.get(item.entity.id)
                    if current is None or current.state.valid_from <= item.state.valid_from:
                        cache[item.entity.id] = item
            return update

    def _process_locked(
        self,
        *,
        scene: SceneModel,
        scene_id: str,
        capture_session_id: str,
        sequence: int,
        captured_at: datetime,
        width: int,
        height: int,
        quality: dict[str, float],
        provider_result: ProviderResult,
        embeddings: dict[str, tuple[float, ...]],
    ) -> WorldFrameUpdate:
        frame = self.repository.create_frame(
            session_id=capture_session_id,
            sequence=sequence,
            captured_at=captured_at,
            width=width,
            height=height,
            quality=quality,
        )

        candidates: list[ObservationCandidate] = []
        evidence_by_observation: dict[str, tuple[str, str | None]] = {}
        provider_by_observation: dict[str, ProviderObservation] = {}
        for provider_observation in provider_result.observations:
            mask_artifact_id: str | None = None
            if scene.persistence_enabled and provider_observation.mask_png is not None:
                stored = self.artifact_store.put_bytes(
                    provider_observation.mask_png,
                    media_type="image/png",
                    kind="segmentation-mask",
                    scene_id=scene_id,
                    session_id=capture_session_id,
                    purpose=f"observation-mask:{sequence}",
                )
                mask_artifact_id = stored.id
            observation = self.repository.create_observation(
                frame_id=frame.id,
                label=provider_observation.label,
                score=provider_observation.confidence,
                box_xyxy=provider_observation.box_xyxy,
                position_m=provider_observation.position_m,
                mask_artifact_id=mask_artifact_id,
            )
            evidence = self.repository.create_evidence(
                scene_id=scene_id,
                kind="observation",
                frame_id=frame.id,
                artifact_id=mask_artifact_id,
                metadata={
                    "observation_id": observation.id,
                    "provider_confidence": provider_observation.confidence,
                },
            )
            candidates.append(
                ObservationCandidate(
                    observation_id=observation.id,
                    label=provider_observation.label,
                    confidence=provider_observation.confidence,
                    box_xyxy=provider_observation.box_xyxy,
                    position_m=provider_observation.position_m,
                    embedding=provider_observation.embedding,
                )
            )
            evidence_by_observation[observation.id] = (evidence.id, mask_artifact_id)
            provider_by_observation[observation.id] = provider_observation

        entities = self.repository.list_entities(scene_id)
        current_states = self.repository.list_current_states(scene_id)
        tracks: list[TrackHypothesis] = []
        previous_states: dict[str, EntityStateModel] = {}
        for entity in entities:
            state = current_states.get(entity.id)
            if state is None or state.box_xyxy is None:
                continue
            previous_states[entity.id] = state
            tracks.append(
                TrackHypothesis(
                    entity_id=entity.id,
                    label=entity.canonical_label,
                    box_xyxy=cast(
                        tuple[float, float, float, float],
                        tuple(float(value) for value in state.box_xyxy),
                    ),
                    position_m=(
                        cast(
                            tuple[float, float, float],
                            tuple(float(value) for value in state.position_m),
                        )
                        if state.position_m is not None
                        else None
                    ),
                    embedding=embeddings.get(entity.id),
                )
            )

        result = associate(tuple(tracks), tuple(candidates), self.association_config)
        candidate_map = {candidate.observation_id: candidate for candidate in candidates}
        entity_map = {entity.id: entity for entity in entities}
        output: list[WorldObject] = []
        events: list[WorldEventModel] = []
        matched_entity_ids: set[str] = set()

        for match in result.matches:
            entity = entity_map[match.entity_id]
            previous = previous_states[match.entity_id]
            candidate = candidate_map[match.observation_id]
            provider_observation = provider_by_observation[match.observation_id]
            current_label = entity.canonical_label.casefold().strip()
            candidate_label = candidate.label.casefold().strip()
            if current_label != candidate_label and (
                current_label == "unknown object" or candidate_label in current_label
            ):
                refined = self.repository.update_entity_label(entity.id, candidate.label)
                if refined is not None:
                    entity = refined
            evidence_id, mask_artifact_id = evidence_by_observation[candidate.observation_id]
            was_missing = previous.presence in {"missing", "occluded"}
            uncertainty = aggregate_uncertainty(
                UncertaintySignals(
                    detector_uncertainty=1.0 - candidate.confidence,
                    mask_instability=0.1 if mask_artifact_id is not None else 0.35,
                    association_ambiguity=1.0 - match.score,
                    geometry_uncertainty=0.2 if candidate.position_m is not None else 0.7,
                    staleness=0.0,
                )
            )
            presence = "rediscovered" if was_missing else "visible"
            state = self.repository.append_entity_state(
                entity_id=entity.id,
                valid_from=captured_at,
                presence=presence,
                confidence=candidate.confidence,
                uncertainty=uncertainty,
                position_m=candidate.position_m,
                quaternion_xyzw=None,
                bounds_m=provider_observation.bounds_m,
                box_xyxy=candidate.box_xyxy,
                evidence_ids=(evidence_id,),
            )
            if candidate.embedding is not None:
                embeddings[entity.id] = candidate.embedding
            event_kind = "rediscovered" if was_missing else self._movement_event(previous, state)
            if event_kind is not None:
                events.append(
                    self.repository.create_event(
                        scene_id=scene_id,
                        entity_id=entity.id,
                        kind=event_kind,
                        occurred_at=captured_at,
                        confidence=min(candidate.confidence, match.score),
                        evidence_ids=(evidence_id,),
                        payload={"association_score": match.score},
                    )
                )
            refreshed_entity = self.repository.get_entity(entity.id)
            if refreshed_entity is None:
                raise RuntimeError("entity disappeared during a state update")
            output.append(WorldObject(refreshed_entity, state, mask_artifact_id))
            matched_entity_ids.add(entity.id)

        for observation_id in result.unmatched_observation_ids:
            candidate = candidate_map[observation_id]
            provider_observation = provider_by_observation[observation_id]
            evidence_id, mask_artifact_id = evidence_by_observation[observation_id]
            layer = "transient" if provider_observation.transient else "persistent"
            entity = self.repository.create_entity(
                scene_id=scene_id,
                label=candidate.label,
                layer=layer,
                observed_at=captured_at,
            )
            uncertainty = aggregate_uncertainty(
                UncertaintySignals(
                    detector_uncertainty=1.0 - candidate.confidence,
                    mask_instability=0.1 if mask_artifact_id is not None else 0.35,
                    association_ambiguity=0.45,
                    geometry_uncertainty=0.2 if candidate.position_m is not None else 0.7,
                    staleness=0.0,
                )
            )
            state = self.repository.append_entity_state(
                entity_id=entity.id,
                valid_from=captured_at,
                presence="visible",
                confidence=candidate.confidence,
                uncertainty=uncertainty,
                position_m=candidate.position_m,
                quaternion_xyzw=None,
                bounds_m=provider_observation.bounds_m,
                box_xyxy=candidate.box_xyxy,
                evidence_ids=(evidence_id,),
            )
            if candidate.embedding is not None:
                embeddings[entity.id] = candidate.embedding
            events.append(
                self.repository.create_event(
                    scene_id=scene_id,
                    entity_id=entity.id,
                    kind="added",
                    occurred_at=captured_at,
                    confidence=candidate.confidence,
                    evidence_ids=(evidence_id,),
                    payload={"label": candidate.label},
                )
            )
            output.append(WorldObject(entity, state, mask_artifact_id))
            matched_entity_ids.add(entity.id)

        for entity in entities:
            if entity.id in matched_entity_ids or entity.layer == "transient":
                continue
            previous = current_states.get(entity.id)
            if previous is None:
                continue
            previous_at = ensure_utc(previous.valid_from)
            if previous_at is None:
                continue
            elapsed = max(0.0, (captured_at - previous_at).total_seconds())
            # Fixed-webcam tracks may briefly disappear between learned
            # discovery passes. An eight-second half-life prevents event spam
            # while still reaching missing after sustained absence.
            confidence = decay_confidence(previous.confidence, elapsed, 8.0)
            occluder = self._occluding_candidate(previous, candidates)
            if occluder is None and elapsed < 5.0:
                # Brief optical-flow or detector gaps are uncertainty, not
                # evidence that a physical object was removed.
                confidence = max(0.25, confidence)
                presence = PresenceState.PREDICTED.value
            else:
                presence = next_presence_state(
                    PresenceState(previous.presence),
                    directly_observed=False,
                    occluded=occluder is not None,
                    confidence=confidence,
                    missing_threshold=0.25,
                ).value
            if presence != previous.presence:
                state = self.repository.append_entity_state(
                    entity_id=entity.id,
                    valid_from=captured_at,
                    presence=presence,
                    confidence=confidence,
                    uncertainty=min(1.0, previous.uncertainty + 0.15),
                    position_m=previous.position_m,
                    quaternion_xyzw=previous.quaternion_xyzw,
                    bounds_m=previous.bounds_m,
                    box_xyxy=previous.box_xyxy,
                    evidence_ids=(),
                )
                output.append(WorldObject(entity, state, None))
                event_kind = (
                    "occluded"
                    if presence == "occluded"
                    else "removed"
                    if presence == "missing"
                    else None
                )
                if event_kind is not None:
                    evidence_ids = (
                        (evidence_by_observation[occluder.observation_id][0],)
                        if occluder is not None
                        else ()
                    )
                    events.append(
                        self.repository.create_event(
                            scene_id=scene_id,
                            entity_id=entity.id,
                            kind=event_kind,
                            occurred_at=captured_at,
                            confidence=confidence,
                            evidence_ids=evidence_ids,
                            payload={"previous_presence": previous.presence},
                        )
                    )

        # Relative depth (and therefore pair topology) is refreshed by learned
        # discovery, while tracking frames only propagate that geometry. Do not
        # close and recreate the scene graph at ordinary 750 ms checkpoints;
        # that turns a static N-object desk into O(N²) durable writes and can
        # starve the live result path on a local SQLite store.
        if provider_result.discovery_ran:
            self._update_relationships(scene_id, captured_at, output)
        return WorldFrameUpdate(objects=tuple(output), events=tuple(events))

    @staticmethod
    def _occluding_candidate(
        previous: EntityStateModel,
        candidates: list[ObservationCandidate],
    ) -> ObservationCandidate | None:
        if previous.box_xyxy is None:
            return None
        x1, y1, x2, y2 = previous.box_xyxy
        previous_area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        if previous_area <= 0.0:
            return None
        best: ObservationCandidate | None = None
        best_coverage = 0.0
        for candidate in candidates:
            cx1, cy1, cx2, cy2 = candidate.box_xyxy
            intersection = max(0.0, min(x2, cx2) - max(x1, cx1)) * max(
                0.0,
                min(y2, cy2) - max(y1, cy1),
            )
            coverage = intersection / previous_area
            if coverage >= 0.55 and coverage > best_coverage:
                best = candidate
                best_coverage = coverage
        return best

    @staticmethod
    def _movement_event(previous: EntityStateModel, current: EntityStateModel) -> str | None:
        if previous.box_xyxy is not None and current.box_xyxy is not None:
            previous_center = (
                (previous.box_xyxy[0] + previous.box_xyxy[2]) / 2,
                (previous.box_xyxy[1] + previous.box_xyxy[3]) / 2,
            )
            current_center = (
                (current.box_xyxy[0] + current.box_xyxy[2]) / 2,
                (current.box_xyxy[1] + current.box_xyxy[3]) / 2,
            )
            pixel_distance = sqrt(
                (previous_center[0] - current_center[0]) ** 2
                + (previous_center[1] - current_center[1]) ** 2
            )
            previous_diagonal = sqrt(
                (previous.box_xyxy[2] - previous.box_xyxy[0]) ** 2
                + (previous.box_xyxy[3] - previous.box_xyxy[1]) ** 2
            )
            if pixel_distance >= max(24.0, previous_diagonal * 0.45):
                return "moved"
        return None

    def _update_relationships(
        self,
        scene_id: str,
        captured_at: datetime,
        objects: list[WorldObject],
    ) -> None:
        positioned = [
            PositionedEntity(
                item.entity.id,
                cast(
                    tuple[float, float, float],
                    tuple(float(value) for value in item.state.position_m),
                ),
            )
            for item in objects
            if item.state.position_m is not None
            and item.state.presence in {"visible", "rediscovered"}
        ]
        relationships: list[tuple[str, str, str, float]] = []
        for subject in positioned:
            for object_ in positioned:
                if subject.entity_id == object_.entity_id:
                    continue
                for candidate in infer_pair_relationships(subject, object_):
                    relationships.append(
                        (
                            candidate.subject_entity_id,
                            candidate.object_entity_id,
                            candidate.relation.value,
                            candidate.confidence,
                        )
                    )
        self.repository.replace_relationships(
            scene_id=scene_id,
            observed_at=captured_at,
            relationships=relationships,
        )
