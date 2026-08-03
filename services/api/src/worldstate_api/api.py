"""Versioned REST API routers."""

from __future__ import annotations

import platform
import subprocess
import sys
from datetime import datetime
from typing import Annotated

import psutil
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from worldstate_api import __version__
from worldstate_api.capture import sniff_video_media_type
from worldstate_api.contracts import (
    BootstrapRequest,
    BootstrapResponse,
    CaptureSessionCreate,
    CaptureSessionResponse,
    DiagnosticsResponse,
    EntityHistoryResponse,
    EntityListResponse,
    EntityResponse,
    EventListResponse,
    GarbageCollectionResponse,
    GpuDiagnostic,
    HealthResponse,
    JobCreate,
    JobListResponse,
    JobResponse,
    LastSeenResponse,
    ModelListResponse,
    RelationshipListResponse,
    ReplayInfo,
    ReplayListResponse,
    SceneCreate,
    SceneListResponse,
    SceneResponse,
    SceneSnapshotResponse,
    SceneUpdate,
    StorageStatsResponse,
    SystemLimits,
    SystemResponse,
    UploadResponse,
)
from worldstate_api.jobs import JobQueueFull
from worldstate_api.providers.registry import ModelManifestError
from worldstate_api.security import (
    SESSION_COOKIE,
    SessionPrincipal,
    require_csrf,
    require_session,
)
from worldstate_api.serialization import (
    capture_session_response,
    entity_history_response,
    entity_response,
    event_response,
    job_response,
    relationship_response,
    scene_response,
)
from worldstate_api.services import AppServices
from worldstate_core.policy import PromptPolicyError, validate_object_prompts

SessionDep = Annotated[SessionPrincipal, Depends(require_session)]
CsrfDep = Annotated[SessionPrincipal, Depends(require_csrf)]


def get_services(request: Request) -> AppServices:
    return request.app.state.services


ServicesDep = Annotated[AppServices, Depends(get_services)]

public_router = APIRouter(tags=["system"])
api_router = APIRouter(prefix="/api/v1")


def not_found(resource: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "not_found", "message": f"{resource} was not found."},
    )


def capture_conflict(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "capture_isolation", "message": message},
    )


def _vector3(value: list[float] | None) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if len(value) != 3:
        raise ValueError("stored position must contain three values")
    return float(value[0]), float(value[1]), float(value[2])


@public_router.get("/healthz")
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="worldstate-api", version=__version__)


@public_router.api_route(
    "/models/hand_landmarker.task",
    methods=["GET", "HEAD"],
    include_in_schema=False,
)
def hand_landmarker_model(services: ServicesDep) -> FileResponse:
    """Serve the checksum-verified gesture model from the local model store."""

    try:
        model_root = services.model_registry.trusted_path("mediapipe-hand-landmarker")
    except (KeyError, ModelManifestError) as error:
        raise not_found("hand landmark model") from error
    model_path = model_root / "hand_landmarker.task"
    if not model_path.is_file():
        raise not_found("hand landmark model")
    return FileResponse(
        model_path,
        media_type="application/octet-stream",
        filename="hand_landmarker.task",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@api_router.get("/system", tags=["system"])
def system(services: ServicesDep) -> SystemResponse:
    settings = services.settings
    return SystemResponse(
        environment=settings.environment,
        persistence_enabled=settings.persistence_enabled,
        protocol_version="v1",
        product_phase="operational",
        provider_mode=settings.provider_mode,
        capabilities=services.capability_states(),
        limits=SystemLimits(
            max_frame_bytes=settings.max_frame_bytes,
            max_frame_width=settings.max_frame_width,
            max_frame_height=settings.max_frame_height,
            max_upload_bytes=settings.max_upload_bytes,
            max_video_duration_seconds=settings.max_video_duration_seconds,
            max_pending_jobs=settings.max_pending_jobs,
            storage_quota_bytes=settings.storage_quota_bytes,
        ),
    )


@api_router.post("/bootstrap", tags=["session"])
def bootstrap(
    payload: BootstrapRequest,
    request: Request,
    response: Response,
    services: ServicesDep,
) -> BootstrapResponse:
    client_key = request.client.host if request.client is not None else "unknown"
    if not services.bootstrap_limiter.allow(client_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many bootstrap attempts."},
        )
    principal = services.sessions.exchange(payload.token)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_bootstrap", "message": "The launcher token is invalid."},
        )
    response.set_cookie(
        SESSION_COOKIE,
        principal.token,
        max_age=services.settings.session_ttl_seconds,
        httponly=True,
        secure=services.settings.secure_cookies,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return BootstrapResponse(
        csrf_token=principal.csrf_token,
        expires_at=principal.expires_at,
    )


@api_router.post("/session/refresh", tags=["session"])
def refresh_session(
    response: Response,
    principal: SessionDep,
) -> BootstrapResponse:
    """Restore the memory-only CSRF capability after a same-origin reload.

    The HttpOnly, SameSite=Strict session cookie authenticates the browser and
    ``OriginValidationMiddleware`` rejects cross-origin POSTs before this
    handler runs. Returning the existing CSRF capability makes normal reloads
    and additional same-origin tabs usable without weakening the cookie
    boundary or putting a secret in browser storage.
    """

    response.headers["Cache-Control"] = "no-store"
    return BootstrapResponse(
        csrf_token=principal.csrf_token,
        expires_at=principal.expires_at,
    )


@api_router.post("/session/logout", status_code=status.HTTP_204_NO_CONTENT, tags=["session"])
def logout(
    response: Response,
    principal: CsrfDep,
    services: ServicesDep,
) -> None:
    services.sessions.revoke(principal.token)
    response.delete_cookie(SESSION_COOKIE, path="/")


@api_router.get("/diagnostics", tags=["system"])
def diagnostics(_principal: SessionDep, services: ServicesDep) -> DiagnosticsResponse:
    memory = psutil.virtual_memory()
    used, count, orphans = services.repository.artifact_stats()
    gpu: GpuDiagnostic | None = None
    try:
        output = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,driver_version",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.splitlines()
        if output:
            name, memory_mib, memory_used_mib, driver = [
                part.strip() for part in output[0].split(",", 3)
            ]
            gpu = GpuDiagnostic(
                name=name,
                memory_total_bytes=int(memory_mib) * 1024 * 1024,
                memory_used_bytes=int(memory_used_mib) * 1024 * 1024,
                driver_version=driver,
                cuda_available=True,
            )
    except (OSError, ValueError, subprocess.SubprocessError):
        gpu = None
    worker_rss: int | None = None
    worker_pid = services.providers.worker_pid
    if worker_pid is not None:
        try:
            worker_rss = int(psutil.Process(worker_pid).memory_info().rss)
        except (psutil.Error, OSError):
            worker_rss = None
    return DiagnosticsResponse(
        platform=platform.system(),
        python_version=sys.version.split()[0],
        cpu_logical_count=psutil.cpu_count(logical=True) or 1,
        memory_total_bytes=int(memory.total),
        memory_available_bytes=int(memory.available),
        api_process_rss_bytes=int(psutil.Process().memory_info().rss),
        inference_worker_rss_bytes=worker_rss,
        live_sessions=services.scheduler.live_sessions,
        pending_jobs=services.repository.count_pending_jobs(),
        gpu=gpu,
        database_ready=services.database.ping(),
        storage=StorageStatsResponse(
            used_bytes=used,
            quota_bytes=services.settings.storage_quota_bytes,
            artifact_count=count,
            orphan_count=orphans,
        ),
    )


@api_router.post("/scenes", status_code=status.HTTP_201_CREATED, tags=["scenes"])
def create_scene(
    payload: SceneCreate,
    _principal: CsrfDep,
    services: ServicesDep,
) -> SceneResponse:
    try:
        prompts = validate_object_prompts(
            payload.object_prompts,
            maximum=services.settings.max_prompts,
        )
    except PromptPolicyError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "prompt_policy", "message": str(error)},
        ) from error
    scene = services.repository.create_scene(
        name=payload.name,
        description=payload.description,
        persistence_enabled=payload.persistence_enabled,
        object_prompts=prompts,
    )
    return scene_response(scene)


@api_router.get("/scenes", tags=["scenes"])
def list_scenes(_principal: SessionDep, services: ServicesDep) -> SceneListResponse:
    return SceneListResponse(
        items=tuple(
            scene_response(scene, entity_count=count)
            for scene, count in services.repository.list_scenes()
        )
    )


@api_router.get("/scenes/{scene_id}", tags=["scenes"])
def get_scene(
    scene_id: str,
    _principal: SessionDep,
    services: ServicesDep,
) -> SceneResponse:
    row = services.repository.get_scene(scene_id)
    if row is None:
        raise not_found("Scene")
    return scene_response(row[0], entity_count=row[1])


@api_router.patch("/scenes/{scene_id}", tags=["scenes"])
def update_scene(
    scene_id: str,
    payload: SceneUpdate,
    _principal: CsrfDep,
    services: ServicesDep,
) -> SceneResponse:
    prompts = payload.object_prompts
    if prompts is not None:
        try:
            prompts = validate_object_prompts(
                prompts,
                maximum=services.settings.max_prompts,
            )
        except PromptPolicyError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "prompt_policy", "message": str(error)},
            ) from error
    scene = services.repository.update_scene(
        scene_id,
        name=payload.name,
        description=payload.description,
        object_prompts=prompts,
        description_was_set="description" in payload.model_fields_set,
    )
    if scene is None:
        raise not_found("Scene")
    count = len(services.repository.list_entities(scene_id))
    return scene_response(scene, entity_count=count)


@api_router.delete(
    "/scenes/{scene_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["scenes"],
)
def delete_scene(
    scene_id: str,
    _principal: CsrfDep,
    services: ServicesDep,
) -> None:
    if not services.repository.delete_scene(scene_id):
        raise not_found("Scene")
    services.artifacts.collect_orphans()


@api_router.post(
    "/scenes/{scene_id}/sessions",
    status_code=status.HTTP_201_CREATED,
    tags=["capture"],
)
def create_capture_session(
    scene_id: str,
    payload: CaptureSessionCreate,
    _principal: CsrfDep,
    services: ServicesDep,
) -> CaptureSessionResponse:
    scene_row = services.repository.get_scene(scene_id)
    if scene_row is None:
        raise not_found("Scene")
    scene, _ = scene_row
    if payload.mode.value == "live":
        if payload.source_name != "browser-webcam":
            raise capture_conflict("Live capture requires the browser-webcam source.")
        if not scene.persistence_enabled:
            raise capture_conflict("Webcam capture requires a persistent live scene.")
        if services.settings.provider_mode != "models":
            raise capture_conflict(
                "Webcam capture requires the learned perception provider; "
                "replay is never substituted."
            )
    elif payload.mode.value == "replay":
        if payload.source_name != "synthetic-desk":
            raise capture_conflict("Replay capture requires the synthetic-desk source.")
        if scene.persistence_enabled:
            raise capture_conflict("Replay capture must use a non-persistent synthetic scene.")
    capture = services.repository.create_capture_session(
        scene_id=scene_id,
        mode=payload.mode.value,
        camera=payload.camera.model_dump(mode="json") if payload.camera else None,
        source_name=payload.source_name,
    )
    if capture is None:
        raise not_found("Scene")
    return capture_session_response(capture)


@api_router.get("/sessions/{session_id}", tags=["capture"])
def get_capture_session(
    session_id: str,
    _principal: SessionDep,
    services: ServicesDep,
) -> CaptureSessionResponse:
    capture = services.repository.get_capture_session(session_id)
    if capture is None:
        raise not_found("Capture session")
    return capture_session_response(capture)


@api_router.post("/sessions/{session_id}/finish", tags=["capture"])
def finish_capture_session(
    session_id: str,
    _principal: CsrfDep,
    services: ServicesDep,
) -> CaptureSessionResponse:
    capture = services.repository.finish_capture_session(session_id)
    if capture is None:
        raise not_found("Capture session")
    return capture_session_response(capture)


@api_router.post(
    "/sessions/{session_id}/video",
    status_code=status.HTTP_201_CREATED,
    tags=["capture"],
)
def upload_video(
    session_id: str,
    _principal: CsrfDep,
    services: ServicesDep,
    upload: Annotated[UploadFile, File(description="MP4 or QuickTime video")],
) -> UploadResponse:
    capture = services.repository.get_capture_session(session_id)
    if capture is None:
        raise not_found("Capture session")
    if capture.mode != "scan":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "wrong_session_mode",
                "message": "Video uploads require a scan session.",
            },
        )
    prefix = upload.file.read(32)
    upload.file.seek(0)
    media_type = sniff_video_media_type(prefix)
    if media_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "invalid_media",
                "message": "Only valid MP4 or MOV files are accepted.",
            },
        )
    if upload.content_type not in {None, media_type, "application/octet-stream"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "code": "media_mismatch",
                "message": "Declared and detected media types differ.",
            },
        )
    artifact = services.artifacts.put_chunks(
        iter(lambda: upload.file.read(1024 * 1024), b""),
        media_type=media_type,
        kind="uploaded-video",
        maximum_bytes=services.settings.max_upload_bytes,
        scene_id=capture.scene_id,
        session_id=capture.id,
        purpose="source-video",
    )
    return UploadResponse(
        artifact_id=artifact.id,
        session_id=session_id,
        media_type=media_type,
        size_bytes=artifact.size_bytes,
        sha256=artifact.sha256,
    )


@api_router.get("/scenes/{scene_id}/entities", tags=["memory"])
def list_entities(
    scene_id: str,
    _principal: SessionDep,
    services: ServicesDep,
    label: Annotated[str | None, Query(max_length=160)] = None,
) -> EntityListResponse:
    if services.repository.get_scene(scene_id) is None:
        raise not_found("Scene")
    entities = services.repository.list_entities(scene_id)
    if label is not None:
        query = label.casefold()
        entities = [
            entity
            for entity in entities
            if query in entity.canonical_label.casefold() or query in entity.display_name.casefold()
        ]
    return EntityListResponse(
        items=tuple(
            entity_response(
                entity,
                current_state=services.repository.get_current_state(entity.id),
            )
            for entity in entities
        )
    )


@api_router.get("/entities/{entity_id}", tags=["memory"])
def get_entity_history(
    entity_id: str,
    _principal: SessionDep,
    services: ServicesDep,
) -> EntityHistoryResponse:
    entity = services.repository.get_entity(entity_id)
    if entity is None:
        raise not_found("Entity")
    return entity_history_response(
        entity,
        services.repository.list_entity_states(entity_id),
    )


@api_router.get("/entities/{entity_id}/last-seen", tags=["memory"])
def last_seen(
    entity_id: str,
    _principal: SessionDep,
    services: ServicesDep,
) -> LastSeenResponse:
    entity = services.repository.get_entity(entity_id)
    if entity is None:
        raise not_found("Entity")
    states = services.repository.list_entity_states(entity_id)
    visible = [state for state in states if state.presence in {"visible", "rediscovered"}]
    state = visible[-1] if visible else None
    return LastSeenResponse(
        entity_id=entity_id,
        last_seen_at=entity.last_seen_at,
        position_m=_vector3(state.position_m) if state else None,
        confidence=state.confidence if state else 0.0,
        evidence_ids=tuple(state.evidence_ids) if state else (),
    )


@api_router.get("/scenes/{scene_id}/events", tags=["memory"])
def list_events(
    scene_id: str,
    _principal: SessionDep,
    services: ServicesDep,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 500,
) -> EventListResponse:
    if services.repository.get_scene(scene_id) is None:
        raise not_found("Scene")
    events = services.repository.list_events(
        scene_id,
        since=since,
        until=until,
        limit=limit,
    )
    return EventListResponse(items=tuple(event_response(event) for event in events))


@api_router.get("/scenes/{scene_id}/relationships", tags=["memory"])
def list_relationships(
    scene_id: str,
    _principal: SessionDep,
    services: ServicesDep,
    at: datetime | None = None,
) -> RelationshipListResponse:
    if services.repository.get_scene(scene_id) is None:
        raise not_found("Scene")
    relationships = services.repository.list_relationships(scene_id, at=at)
    return RelationshipListResponse(
        items=tuple(relationship_response(item) for item in relationships)
    )


@api_router.get("/scenes/{scene_id}/snapshot", tags=["memory"])
def scene_snapshot(
    scene_id: str,
    at: datetime,
    _principal: SessionDep,
    services: ServicesDep,
) -> SceneSnapshotResponse:
    if services.repository.get_scene(scene_id) is None:
        raise not_found("Scene")
    entities = services.repository.list_entities(scene_id, at=at)
    entity_items: list[EntityResponse] = []
    for entity in entities:
        state = services.repository.get_current_state(entity.id, at=at)
        if state is not None:
            entity_items.append(entity_response(entity, current_state=state))
    relationships = services.repository.list_relationships(scene_id, at=at)
    return SceneSnapshotResponse(
        scene_id=scene_id,
        at=at,
        entities=tuple(entity_items),
        relationships=tuple(relationship_response(item) for item in relationships),
    )


@api_router.post("/jobs", status_code=status.HTTP_202_ACCEPTED, tags=["jobs"])
def create_job(
    payload: JobCreate,
    _principal: CsrfDep,
    services: ServicesDep,
) -> JobResponse:
    if payload.scene_id is not None and services.repository.get_scene(payload.scene_id) is None:
        raise not_found("Scene")
    if (
        payload.session_id is not None
        and services.repository.get_capture_session(payload.session_id) is None
    ):
        raise not_found("Capture session")
    if payload.kind.value in {"scan", "reconstruction"}:
        artifact_id = payload.parameters.get("video_artifact_id")
        if (
            not isinstance(artifact_id, str)
            or services.repository.get_artifact(artifact_id) is None
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "video_artifact_required",
                    "message": "A valid uploaded video artifact is required.",
                },
            )
    if payload.kind.value == "evaluation":
        manifest = payload.parameters.get("manifest")
        artifact_id = payload.parameters.get("manifest_artifact_id")
        if not isinstance(manifest, dict) and not isinstance(artifact_id, str):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "evaluation_manifest_required",
                    "message": "A versioned inline manifest or artifact ID is required.",
                },
            )
    try:
        job = services.jobs.submit(
            kind=payload.kind.value,
            scene_id=payload.scene_id,
            session_id=payload.session_id,
            parameters=payload.parameters,
        )
    except JobQueueFull as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "job_queue_full", "message": str(error)},
        ) from error
    return job_response(job)


@api_router.get("/jobs", tags=["jobs"])
def list_jobs(_principal: SessionDep, services: ServicesDep) -> JobListResponse:
    return JobListResponse(
        items=tuple(job_response(job) for job in services.repository.list_jobs())
    )


@api_router.get("/jobs/{job_id}", tags=["jobs"])
def get_job(
    job_id: str,
    _principal: SessionDep,
    services: ServicesDep,
) -> JobResponse:
    job = services.repository.get_job(job_id)
    if job is None:
        raise not_found("Job")
    return job_response(job)


@api_router.post("/jobs/{job_id}/cancel", tags=["jobs"])
def cancel_job(
    job_id: str,
    _principal: CsrfDep,
    services: ServicesDep,
) -> JobResponse:
    job = services.jobs.cancel(job_id)
    if job is None:
        raise not_found("Job")
    return job_response(job)


@api_router.get("/models", tags=["models"])
def list_models(_principal: SessionDep, services: ServicesDep) -> ModelListResponse:
    return ModelListResponse(
        items=services.model_registry.list_models(verify_checksums=False),
    )


@api_router.get("/storage", tags=["storage"])
def storage_stats(_principal: SessionDep, services: ServicesDep) -> StorageStatsResponse:
    used, count, orphan_count = services.repository.artifact_stats()
    return StorageStatsResponse(
        used_bytes=used,
        quota_bytes=services.settings.storage_quota_bytes,
        artifact_count=count,
        orphan_count=orphan_count,
    )


@api_router.post("/storage/garbage-collect", tags=["storage"])
def garbage_collect(
    _principal: CsrfDep,
    services: ServicesDep,
) -> GarbageCollectionResponse:
    removed, reclaimed = services.artifacts.collect_orphans()
    return GarbageCollectionResponse(
        removed_artifacts=removed,
        reclaimed_bytes=reclaimed,
    )


@api_router.get("/artifacts/{artifact_id}", tags=["artifacts"])
def download_artifact(
    artifact_id: str,
    _principal: SessionDep,
    services: ServicesDep,
) -> FileResponse:
    record = services.repository.get_artifact(artifact_id)
    if record is None:
        raise not_found("Artifact")
    path = services.artifacts.resolve_trusted_path(artifact_id)
    return FileResponse(
        path,
        media_type=record.media_type,
        filename=f"{artifact_id}.{_safe_extension(record.media_type)}",
        headers={"Cache-Control": "private, no-store"},
    )


@api_router.get("/replays", tags=["replay"])
def list_replays(_principal: SessionDep) -> ReplayListResponse:
    return ReplayListResponse(
        items=(
            ReplayInfo(
                id="desk-change-v1",
                name="Desk Change",
                description="Deterministic object movement, disappearance, and rediscovery.",
                duration_seconds=24.0,
                frame_count=240,
                protocol_version="v1",
            ),
        )
    )


def _safe_extension(media_type: str) -> str:
    return {
        "application/json": "json",
        "image/jpeg": "jpg",
        "image/png": "png",
        "model/gltf-binary": "glb",
        "model/ply": "ply",
        "video/mp4": "mp4",
        "video/quicktime": "mov",
    }.get(media_type, "bin")
