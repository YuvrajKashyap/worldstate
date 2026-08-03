"""Explicit ORM-to-contract serialization boundaries."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from worldstate_api.contracts import (
    CameraIntrinsics,
    CaptureSessionResponse,
    EntityHistoryResponse,
    EntityLayerValue,
    EntityResponse,
    EntityStateResponse,
    EventKindValue,
    JobKind,
    JobResponse,
    JobStatus,
    Presence,
    RelationshipResponse,
    SceneResponse,
    SessionMode,
    SessionStatus,
    WorldEventResponse,
)
from worldstate_api.persistence import (
    CaptureSessionModel,
    EntityModel,
    EntityStateModel,
    JobModel,
    RelationshipModel,
    SceneModel,
    WorldEventModel,
    ensure_utc,
)


def _required_utc(value: datetime) -> datetime:
    converted = ensure_utc(value)
    if converted is None:
        raise ValueError("required database timestamp is missing")
    return converted


def _vector3(value: list[float] | None) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if len(value) != 3:
        raise ValueError("stored vector must contain three values")
    return float(value[0]), float(value[1]), float(value[2])


def _quaternion(value: list[float] | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if len(value) != 4:
        raise ValueError("stored quaternion must contain four values")
    return float(value[0]), float(value[1]), float(value[2]), float(value[3])


def _box(value: list[float] | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if len(value) != 4:
        raise ValueError("stored box must contain four values")
    return float(value[0]), float(value[1]), float(value[2]), float(value[3])


def scene_response(scene: SceneModel, *, entity_count: int = 0) -> SceneResponse:
    return SceneResponse(
        id=scene.id,
        name=scene.name,
        description=scene.description,
        persistence_enabled=scene.persistence_enabled,
        object_prompts=tuple(scene.object_prompts),
        coordinate_frame="worldstate_scene_v1",
        created_at=_required_utc(scene.created_at),
        updated_at=_required_utc(scene.updated_at),
        entity_count=entity_count,
    )


def capture_session_response(capture: CaptureSessionModel) -> CaptureSessionResponse:
    return CaptureSessionResponse(
        id=capture.id,
        scene_id=capture.scene_id,
        mode=SessionMode(capture.mode),
        status=SessionStatus(capture.status),
        camera=CameraIntrinsics.model_validate(capture.camera) if capture.camera else None,
        source_name=capture.source_name,
        started_at=ensure_utc(capture.started_at),
        ended_at=ensure_utc(capture.ended_at),
        created_at=_required_utc(capture.created_at),
    )


def entity_state_response(state: EntityStateModel) -> EntityStateResponse:
    return EntityStateResponse(
        id=state.id,
        entity_id=state.entity_id,
        valid_from=_required_utc(state.valid_from),
        valid_to=ensure_utc(state.valid_to),
        presence=Presence(state.presence),
        confidence=state.confidence,
        uncertainty=state.uncertainty,
        position_m=_vector3(state.position_m),
        quaternion_xyzw=_quaternion(state.quaternion_xyzw),
        bounds_m=_vector3(state.bounds_m),
        box_xyxy=_box(state.box_xyxy),
        evidence_ids=tuple(state.evidence_ids),
    )


def entity_response(
    entity: EntityModel,
    *,
    current_state: EntityStateModel | None,
) -> EntityResponse:
    return EntityResponse(
        id=entity.id,
        scene_id=entity.scene_id,
        canonical_label=entity.canonical_label,
        display_name=entity.display_name,
        layer=EntityLayerValue(entity.layer),
        status=Presence(current_state.presence if current_state is not None else entity.status),
        created_at=_required_utc(entity.created_at),
        last_seen_at=ensure_utc(entity.last_seen_at),
        current_state=entity_state_response(current_state) if current_state else None,
    )


def entity_history_response(
    entity: EntityModel,
    states: list[EntityStateModel],
) -> EntityHistoryResponse:
    current = states[-1] if states else None
    return EntityHistoryResponse(
        entity=entity_response(entity, current_state=current),
        states=tuple(entity_state_response(state) for state in states),
    )


def event_response(event: WorldEventModel) -> WorldEventResponse:
    return WorldEventResponse(
        id=event.id,
        scene_id=event.scene_id,
        entity_id=event.entity_id,
        kind=EventKindValue(event.kind),
        occurred_at=_required_utc(event.occurred_at),
        confidence=event.confidence,
        evidence_ids=tuple(event.evidence_ids),
        payload=event.payload,
    )


def relationship_response(relationship: RelationshipModel) -> RelationshipResponse:
    return RelationshipResponse(
        id=relationship.id,
        scene_id=relationship.scene_id,
        subject_entity_id=relationship.subject_entity_id,
        object_entity_id=relationship.object_entity_id,
        kind=cast(
            Literal["left_of", "right_of", "above", "below", "near", "inside", "on"],
            relationship.kind,
        ),
        confidence=relationship.confidence,
        valid_from=_required_utc(relationship.valid_from),
        valid_to=ensure_utc(relationship.valid_to),
    )


def job_response(job: JobModel) -> JobResponse:
    return JobResponse(
        id=job.id,
        kind=JobKind(job.kind),
        status=JobStatus(job.status),
        scene_id=job.scene_id,
        session_id=job.session_id,
        progress=job.progress,
        stage=job.stage,
        result=job.result,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=_required_utc(job.created_at),
        started_at=ensure_utc(job.started_at),
        finished_at=ensure_utc(job.finished_at),
        cancellation_requested=job.cancellation_requested,
    )
