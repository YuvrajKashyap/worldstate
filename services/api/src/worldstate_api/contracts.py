"""Versioned public API and WebSocket contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROTOCOL_VERSION = "v1"
PublicId = Annotated[str, Field(min_length=36, max_length=36)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
Vector3 = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]
BoxXYXY = tuple[float, float, float, float]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class HealthResponse(StrictModel):
    status: Literal["ok"]
    service: Literal["worldstate-api"]
    version: str


class CapabilityState(StrEnum):
    READY = "ready"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class SystemLimits(StrictModel):
    max_frame_bytes: int
    max_frame_width: int
    max_frame_height: int
    max_upload_bytes: int
    max_video_duration_seconds: int
    max_pending_jobs: int
    storage_quota_bytes: int


class SystemResponse(StrictModel):
    environment: str
    persistence_enabled: bool
    protocol_version: Literal["v1"]
    product_phase: Literal["operational"]
    provider_mode: Literal["replay", "classical", "models"]
    capabilities: dict[str, CapabilityState]
    limits: SystemLimits


class BootstrapRequest(StrictModel):
    token: str = Field(min_length=32, max_length=256)


class BootstrapResponse(StrictModel):
    csrf_token: str
    expires_at: datetime
    protocol_version: Literal["v1"] = "v1"


class SceneCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    persistence_enabled: bool = False
    object_prompts: tuple[str, ...] = (
        "laptop",
        "keyboard",
        "computer mouse",
        "bottle",
        "notebook",
    )


class SceneUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    object_prompts: tuple[str, ...] | None = None


class SceneResponse(StrictModel):
    id: PublicId
    name: str
    description: str | None
    persistence_enabled: bool
    object_prompts: tuple[str, ...]
    coordinate_frame: Literal["worldstate_scene_v1"]
    created_at: datetime
    updated_at: datetime
    entity_count: int = 0


class SceneListResponse(StrictModel):
    items: tuple[SceneResponse, ...]


class SessionMode(StrEnum):
    LIVE = "live"
    SCAN = "scan"
    REPLAY = "replay"


class SessionStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CameraIntrinsics(StrictModel):
    width: int = Field(ge=1, le=7680)
    height: int = Field(ge=1, le=4320)
    fx: float | None = Field(default=None, gt=0)
    fy: float | None = Field(default=None, gt=0)
    cx: float | None = None
    cy: float | None = None
    distortion: tuple[float, ...] = Field(default=(), max_length=14)


class CaptureSessionCreate(StrictModel):
    mode: SessionMode
    camera: CameraIntrinsics | None = None
    source_name: str | None = Field(default=None, min_length=1, max_length=160)


class CaptureSessionResponse(StrictModel):
    id: PublicId
    scene_id: PublicId
    mode: SessionMode
    status: SessionStatus
    camera: CameraIntrinsics | None
    source_name: str | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime


class Presence(StrEnum):
    VISIBLE = "visible"
    OCCLUDED = "occluded"
    PREDICTED = "predicted"
    MISSING = "missing"
    REDISCOVERED = "rediscovered"
    ARCHIVED = "archived"


class EntityLayerValue(StrEnum):
    STATIC = "static"
    PERSISTENT = "persistent"
    TRANSIENT = "transient"


class EntityStateResponse(StrictModel):
    id: PublicId
    entity_id: PublicId
    valid_from: datetime
    valid_to: datetime | None
    presence: Presence
    confidence: Confidence
    uncertainty: Confidence
    position_m: Vector3 | None
    quaternion_xyzw: Quaternion | None
    bounds_m: Vector3 | None
    box_xyxy: BoxXYXY | None
    evidence_ids: tuple[PublicId, ...]


class EntityResponse(StrictModel):
    id: PublicId
    scene_id: PublicId
    canonical_label: str
    display_name: str
    layer: EntityLayerValue
    status: Presence
    created_at: datetime
    last_seen_at: datetime | None
    current_state: EntityStateResponse | None = None


class EntityListResponse(StrictModel):
    items: tuple[EntityResponse, ...]


class EntityHistoryResponse(StrictModel):
    entity: EntityResponse
    states: tuple[EntityStateResponse, ...]


class EventKindValue(StrEnum):
    ADDED = "added"
    MOVED = "moved"
    ROTATED = "rotated"
    REMOVED = "removed"
    OCCLUDED = "occluded"
    REDISCOVERED = "rediscovered"
    CONFIDENCE_CHANGED = "confidence_changed"


class WorldEventResponse(StrictModel):
    id: PublicId
    scene_id: PublicId
    entity_id: PublicId
    kind: EventKindValue
    occurred_at: datetime
    confidence: Confidence
    evidence_ids: tuple[PublicId, ...]
    payload: dict[str, object]


class EventListResponse(StrictModel):
    items: tuple[WorldEventResponse, ...]


class RelationshipResponse(StrictModel):
    id: PublicId
    scene_id: PublicId
    subject_entity_id: PublicId
    object_entity_id: PublicId
    kind: Literal["left_of", "right_of", "above", "below", "near", "inside", "on"]
    confidence: Confidence
    valid_from: datetime
    valid_to: datetime | None


class RelationshipListResponse(StrictModel):
    items: tuple[RelationshipResponse, ...]


class SceneSnapshotResponse(StrictModel):
    scene_id: PublicId
    at: datetime
    entities: tuple[EntityResponse, ...]
    relationships: tuple[RelationshipResponse, ...]


class LastSeenResponse(StrictModel):
    entity_id: PublicId
    last_seen_at: datetime | None
    position_m: Vector3 | None
    confidence: Confidence
    evidence_ids: tuple[PublicId, ...]


class JobKind(StrEnum):
    SCAN = "scan"
    RECONSTRUCTION = "reconstruction"
    EVALUATION = "evaluation"
    EXPORT = "export"
    GARBAGE_COLLECTION = "garbage_collection"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


class JobCreate(StrictModel):
    kind: JobKind
    scene_id: PublicId | None = None
    session_id: PublicId | None = None
    parameters: dict[str, object] = Field(default_factory=dict)


class JobResponse(StrictModel):
    id: PublicId
    kind: JobKind
    status: JobStatus
    scene_id: PublicId | None
    session_id: PublicId | None
    progress: Confidence
    stage: str
    result: dict[str, object] | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cancellation_requested: bool


class JobListResponse(StrictModel):
    items: tuple[JobResponse, ...]


class ModelState(StrEnum):
    AVAILABLE = "available"
    NOT_INSTALLED = "not_installed"
    DISABLED = "disabled"
    INVALID = "invalid"


class ModelInfo(StrictModel):
    id: str
    display_name: str
    capability: str
    license: str
    source: str
    revision: str
    state: ModelState
    required: bool
    gated: bool
    approximate_size_bytes: int | None


class ModelListResponse(StrictModel):
    items: tuple[ModelInfo, ...]


class StorageStatsResponse(StrictModel):
    used_bytes: int
    quota_bytes: int
    artifact_count: int
    orphan_count: int


class GpuDiagnostic(StrictModel):
    name: str
    memory_total_bytes: int | None
    memory_used_bytes: int | None
    driver_version: str | None
    cuda_available: bool


class DiagnosticsResponse(StrictModel):
    platform: str
    python_version: str
    cpu_logical_count: int
    memory_total_bytes: int
    memory_available_bytes: int
    api_process_rss_bytes: int
    inference_worker_rss_bytes: int | None
    live_sessions: int
    pending_jobs: int
    gpu: GpuDiagnostic | None
    database_ready: bool
    storage: StorageStatsResponse


class GarbageCollectionResponse(StrictModel):
    removed_artifacts: int
    reclaimed_bytes: int


class UploadResponse(StrictModel):
    artifact_id: PublicId
    session_id: PublicId
    media_type: Literal["video/mp4", "video/quicktime"]
    size_bytes: int
    sha256: str


class ExportCreate(StrictModel):
    scene_id: PublicId
    formats: tuple[Literal["manifest", "glb", "ply", "timeline"]] = ("manifest",)


class ExportResponse(StrictModel):
    id: PublicId
    scene_id: PublicId
    status: JobStatus
    artifact_ids: tuple[PublicId, ...]
    created_at: datetime


class ReplayInfo(StrictModel):
    id: str
    name: str
    description: str
    duration_seconds: float
    frame_count: int
    protocol_version: Literal["v1"]


class ReplayListResponse(StrictModel):
    items: tuple[ReplayInfo, ...]


class ErrorDetail(StrictModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(StrictModel):
    error: ErrorDetail


class ClientHello(StrictModel):
    type: Literal["client.hello"]
    protocol_version: Literal["v1"]
    request_id: str = Field(min_length=1, max_length=120)
    session_id: PublicId
    prompts: tuple[str, ...] = ()
    requested_capabilities: tuple[str, ...] = ()


class ServerReady(StrictModel):
    type: Literal["server.ready"] = "server.ready"
    protocol_version: Literal["v1"] = "v1"
    request_id: str
    accepted_capabilities: tuple[str, ...]
    provider_mode: Literal["replay", "classical", "models"]
    limits: SystemLimits


class FrameObject(StrictModel):
    entity_id: PublicId
    label: str
    confidence: Confidence
    uncertainty: Confidence
    presence: Presence
    box_xyxy: BoxXYXY
    position_m: Vector3 | None
    bounds_m: Vector3 | None
    mask_artifact_id: PublicId | None = None


class FrameMetrics(StrictModel):
    sequence: int = Field(ge=0)
    capture_to_result_ms: float = Field(ge=0)
    inference_ms: float = Field(ge=0)
    queue_depth: Literal[0, 1]
    dropped_frames: int = Field(ge=0)
    discovery_ran: bool
    depth_ran: bool
    embedding_ran: bool
    gpu_allocated_bytes: int | None = Field(default=None, ge=0)
    gpu_reserved_bytes: int | None = Field(default=None, ge=0)


class FrameResult(StrictModel):
    type: Literal["frame.result"] = "frame.result"
    protocol_version: Literal["v1"] = "v1"
    request_id: str
    sequence: int = Field(ge=0)
    captured_at: datetime
    presented_at: datetime
    objects: tuple[FrameObject, ...]
    events: tuple[WorldEventResponse, ...]
    metrics: FrameMetrics
    quality: dict[str, float]


class WorldPatch(StrictModel):
    type: Literal["world.patch"] = "world.patch"
    protocol_version: Literal["v1"] = "v1"
    request_id: str
    scene_id: PublicId
    sequence: int = Field(ge=0)
    entities: tuple[FrameObject, ...]


class EventBatch(StrictModel):
    type: Literal["event.batch"] = "event.batch"
    protocol_version: Literal["v1"] = "v1"
    request_id: str
    scene_id: PublicId
    sequence: int = Field(ge=0)
    events: tuple[WorldEventResponse, ...]


class CommandName(StrEnum):
    SELECT_ENTITY = "select_entity"
    PIN_ENTITY = "pin_entity"
    SET_ENTITY_VISIBILITY = "set_entity_visibility"
    SET_TIMELINE_TIME = "set_timeline_time"
    QUERY_ENTITY = "query_entity"
    FIND_LAST_SEEN = "find_last_seen"
    START_SCAN = "start_scan"
    CANCEL_JOB = "cancel_job"


class CommandSubmit(StrictModel):
    type: Literal["command.submit"]
    protocol_version: Literal["v1"]
    request_id: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=16, max_length=120)
    command: CommandName
    scene_id: PublicId
    entity_id: PublicId | None = None
    expected_entity_state_id: PublicId | None = None
    arguments: dict[str, object] = Field(default_factory=dict)


class CommandResult(StrictModel):
    type: Literal["command.result"] = "command.result"
    protocol_version: Literal["v1"] = "v1"
    request_id: str
    idempotency_key: str
    status: Literal["accepted", "completed", "rejected"]
    result: dict[str, object] = Field(default_factory=dict)


class FlowSlowDown(StrictModel):
    type: Literal["flow.slow_down"] = "flow.slow_down"
    protocol_version: Literal["v1"] = "v1"
    request_id: str
    retry_after_ms: int = Field(ge=1, le=10_000)
    reason: Literal["busy", "live_session_active", "resource_limit"]


class WebSocketError(StrictModel):
    type: Literal["error"] = "error"
    protocol_version: Literal["v1"] = "v1"
    request_id: str | None
    code: str
    message: str
    recoverable: bool


class FrameEnvelopeMetadata(StrictModel):
    """Documented representation of the fixed-width binary frame header."""

    magic: Literal["WSF1"] = "WSF1"
    sequence: int = Field(ge=0)
    captured_at_unix_seconds: float = Field(ge=0)
    width: int = Field(ge=1, le=7680)
    height: int = Field(ge=1, le=4320)
    encoding: Literal["jpeg", "webp", "rgba", "i420"]

    @field_validator("captured_at_unix_seconds")
    @classmethod
    def require_finite_timestamp(cls, value: float) -> float:
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("capture timestamp must be finite")
        return value
