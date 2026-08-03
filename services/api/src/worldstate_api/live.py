"""Authenticated, bounded live-frame WebSocket protocol."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from time import perf_counter

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from worldstate_api.capture import FrameProtocolError, decode_frame, unpack_frame
from worldstate_api.contracts import (
    ClientHello,
    CommandResult,
    CommandSubmit,
    EventBatch,
    FlowSlowDown,
    FrameMetrics,
    FrameObject,
    FrameResult,
    Presence,
    ServerReady,
    SystemLimits,
    WebSocketError,
    WorldPatch,
)
from worldstate_api.jobs import JobQueueFull
from worldstate_api.providers.temporal import TemporalObservationFilter
from worldstate_api.runtime import RuntimeBusyError
from worldstate_api.security import authenticate_websocket
from worldstate_api.serialization import event_response
from worldstate_api.services import AppServices
from worldstate_api.world_engine import WorldFrameUpdate
from worldstate_core.policy import PromptPolicyError, validate_object_prompts

live_router = APIRouter()
_PERSIST_INTERVAL = timedelta(milliseconds=750)


def _box(value: list[float] | None) -> tuple[float, float, float, float]:
    if value is None:
        return 0.0, 0.0, 0.0, 0.0
    if len(value) != 4:
        raise ValueError("stored box must contain four values")
    return float(value[0]), float(value[1]), float(value[2]), float(value[3])


def _position(value: list[float] | None) -> tuple[float, float, float] | None:
    if value is None:
        return None
    if len(value) != 3:
        raise ValueError("stored position must contain three values")
    return float(value[0]), float(value[1]), float(value[2])


def _diagnostic_bytes(diagnostics: Mapping[str, object], key: str) -> int | None:
    value = diagnostics.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


async def _send_error(
    websocket: WebSocket,
    *,
    code: str,
    message: str,
    request_id: str | None = None,
    recoverable: bool = True,
) -> None:
    await websocket.send_text(
        WebSocketError(
            request_id=request_id,
            code=code,
            message=message,
            recoverable=recoverable,
        ).model_dump_json()
    )


@live_router.websocket("/api/v1/live")
async def live(websocket: WebSocket) -> None:
    services: AppServices = websocket.app.state.services
    settings = services.settings
    principal = authenticate_websocket(websocket, settings)
    if principal is None:
        await websocket.close(code=4403, reason="Origin or local session rejected")
        return

    await websocket.accept()
    provider = None
    scheduler_owned = False
    capture_session_id: str | None = None
    pending_checkpoint: asyncio.Task[WorldFrameUpdate] | None = None
    failed = False
    try:
        raw_hello = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        if len(raw_hello) > 64_000:
            raise ValueError("hello message exceeds the protocol limit")
        hello = ClientHello.model_validate_json(raw_hello)
        capture = services.repository.get_capture_session(hello.session_id)
        if capture is None or capture.mode not in {"live", "replay"} or capture.status != "created":
            await _send_error(
                websocket,
                code="invalid_session",
                message="A live or replay capture session is required.",
                request_id=hello.request_id,
                recoverable=False,
            )
            await websocket.close(code=4404)
            return
        scene_row = services.repository.get_scene(capture.scene_id)
        if scene_row is None:
            await websocket.close(code=4404)
            return
        scene, _ = scene_row
        valid_capture = (
            capture.mode == "live"
            and capture.source_name == "browser-webcam"
            and scene.persistence_enabled
            and settings.provider_mode == "models"
        ) or (
            capture.mode == "replay"
            and capture.source_name == "synthetic-desk"
            and not scene.persistence_enabled
        )
        if not valid_capture:
            await _send_error(
                websocket,
                code="capture_isolation",
                message=(
                    "The capture source, scene, and perception provider do not form "
                    "a valid session."
                ),
                request_id=hello.request_id,
                recoverable=False,
            )
            await websocket.close(code=4409)
            return
        try:
            prompts = validate_object_prompts(
                hello.prompts or tuple(scene.object_prompts),
                maximum=settings.max_prompts,
            )
        except PromptPolicyError as error:
            await _send_error(
                websocket,
                code="prompt_policy",
                message=str(error),
                request_id=hello.request_id,
                recoverable=False,
            )
            await websocket.close(code=4400)
            return

        selected_provider_mode = "replay" if capture.mode == "replay" else settings.provider_mode
        if selected_provider_mode == "models":
            try:
                services.scheduler.start_live()
                scheduler_owned = True
            except RuntimeBusyError:
                await websocket.send_text(
                    FlowSlowDown(
                        request_id=hello.request_id,
                        retry_after_ms=1000,
                        reason="busy",
                    ).model_dump_json()
                )
                await websocket.close(code=4429)
                return

        capture = services.repository.activate_capture_session(capture.id)
        if capture is None:
            await websocket.close(code=4404)
            return
        capture_session_id = capture.id
        provider = services.providers.create(selected_provider_mode)
        temporal_filter = TemporalObservationFilter() if capture.mode == "live" else None
        supported_capabilities = (
            "frame.result",
            "world.patch",
            "event.batch",
            "command.submit",
        )
        requested_capabilities = set(hello.requested_capabilities)
        accepted_capabilities = (
            supported_capabilities
            if not requested_capabilities
            else tuple(
                capability
                for capability in supported_capabilities
                if capability in requested_capabilities or capability == "frame.result"
            )
        )
        emit_world_patch = "world.patch" in accepted_capabilities
        emit_event_batch = "event.batch" in accepted_capabilities
        await websocket.send_text(
            ServerReady(
                request_id=hello.request_id,
                accepted_capabilities=accepted_capabilities,
                provider_mode=selected_provider_mode,
                limits=SystemLimits(
                    max_frame_bytes=settings.max_frame_bytes,
                    max_frame_width=settings.max_frame_width,
                    max_frame_height=settings.max_frame_height,
                    max_upload_bytes=settings.max_upload_bytes,
                    max_video_duration_seconds=settings.max_video_duration_seconds,
                    max_pending_jobs=settings.max_pending_jobs,
                    storage_quota_bytes=settings.storage_quota_bytes,
                ),
            ).model_dump_json()
        )

        last_sequence = -1
        last_captured_at: datetime | None = None
        last_persisted_at: datetime | None = None
        dropped_frames = 0
        idempotency_results: dict[str, CommandResult] = {}
        durable_initialized = False
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            text = message.get("text")
            if text is not None:
                if len(text) > 64_000:
                    await _send_error(
                        websocket,
                        code="message_too_large",
                        message="Control messages cannot exceed 64 KB.",
                    )
                    continue
                await _handle_command(
                    websocket,
                    text=text,
                    services=services,
                    cache=idempotency_results,
                )
                continue
            binary = message.get("bytes")
            if binary is None:
                continue

            started = perf_counter()
            try:
                packet = unpack_frame(
                    binary,
                    maximum_bytes=settings.max_frame_bytes,
                    maximum_width=settings.max_frame_width,
                    maximum_height=settings.max_frame_height,
                )
                if packet.sequence <= last_sequence:
                    raise FrameProtocolError("frame sequence must increase monotonically")
                now = datetime.now(UTC)
                if packet.captured_at > now + timedelta(seconds=10):
                    raise FrameProtocolError("frame timestamp is unexpectedly in the future")
                if packet.captured_at < now - timedelta(minutes=30):
                    raise FrameProtocolError("frame timestamp is too old for a live session")
                if last_captured_at is not None and packet.captured_at <= last_captured_at:
                    raise FrameProtocolError("frame timestamps must increase monotonically")
                if last_sequence >= 0:
                    dropped_frames += max(0, packet.sequence - last_sequence - 1)
                decoded = await asyncio.to_thread(decode_frame, packet)
                provider_result = await asyncio.to_thread(
                    provider.observe,
                    decoded.bgr,
                    sequence=packet.sequence,
                    prompts=prompts,
                )
                if temporal_filter is not None:
                    provider_result = temporal_filter.apply(
                        provider_result,
                        sequence=packet.sequence,
                    )
                checkpoint_events = ()
                if pending_checkpoint is not None and pending_checkpoint.done():
                    try:
                        checkpoint_update = pending_checkpoint.result()
                        checkpoint_events = checkpoint_update.events
                    except Exception:
                        failed = True
                        await _send_error(
                            websocket,
                            code="persistence_failed",
                            message="Live tracking is active, but its durable checkpoint failed.",
                            request_id=f"frame-{packet.sequence}",
                        )
                    pending_checkpoint = None
                persist_frame = (
                    last_persisted_at is None
                    or provider_result.discovery_ran
                    or packet.captured_at - last_persisted_at >= _PERSIST_INTERVAL
                )
                if not durable_initialized:
                    update = await asyncio.to_thread(
                        services.world_engine.process,
                        scene_id=capture.scene_id,
                        capture_session_id=capture.id,
                        sequence=packet.sequence,
                        captured_at=packet.captured_at,
                        width=packet.width,
                        height=packet.height,
                        quality=decoded.quality,
                        provider_result=provider_result,
                    )
                    durable_initialized = True
                    last_persisted_at = packet.captured_at
                else:
                    update = await asyncio.to_thread(
                        services.world_engine.process_ephemeral,
                        scene_id=capture.scene_id,
                        captured_at=packet.captured_at,
                        provider_result=provider_result,
                    )
                    if persist_frame and pending_checkpoint is None:
                        pending_checkpoint = asyncio.create_task(
                            asyncio.to_thread(
                                services.world_engine.process,
                                scene_id=capture.scene_id,
                                capture_session_id=capture.id,
                                sequence=packet.sequence,
                                captured_at=packet.captured_at,
                                width=packet.width,
                                height=packet.height,
                                quality=decoded.quality,
                                provider_result=provider_result,
                            )
                        )
                        last_persisted_at = packet.captured_at
                presented_at = datetime.now(UTC)
                objects = tuple(
                    FrameObject(
                        entity_id=item.entity.id,
                        label=item.entity.display_name,
                        confidence=item.state.confidence,
                        uncertainty=item.state.uncertainty,
                        presence=Presence(item.state.presence),
                        box_xyxy=_box(item.state.box_xyxy),
                        position_m=_position(item.state.position_m),
                        bounds_m=_position(item.state.bounds_m),
                        mask_artifact_id=item.mask_artifact_id,
                    )
                    for item in update.objects
                )
                result = FrameResult(
                    request_id=f"frame-{packet.sequence}",
                    sequence=packet.sequence,
                    captured_at=packet.captured_at,
                    presented_at=presented_at,
                    objects=objects,
                    events=tuple(
                        event_response(item) for item in (*checkpoint_events, *update.events)
                    ),
                    metrics=FrameMetrics(
                        sequence=packet.sequence,
                        capture_to_result_ms=max(
                            0.0,
                            (presented_at - packet.captured_at).total_seconds() * 1000.0,
                        ),
                        inference_ms=provider_result.inference_ms,
                        queue_depth=0,
                        dropped_frames=dropped_frames,
                        discovery_ran=provider_result.discovery_ran,
                        depth_ran=provider_result.depth_ran,
                        embedding_ran=provider_result.embedding_ran,
                        gpu_allocated_bytes=_diagnostic_bytes(
                            provider_result.diagnostics,
                            "gpu_allocated_bytes",
                        ),
                        gpu_reserved_bytes=_diagnostic_bytes(
                            provider_result.diagnostics,
                            "gpu_reserved_bytes",
                        ),
                    ),
                    quality=decoded.quality,
                )
                if emit_world_patch:
                    await websocket.send_text(
                        WorldPatch(
                            request_id=f"patch-{packet.sequence}",
                            scene_id=capture.scene_id,
                            sequence=packet.sequence,
                            entities=objects,
                        ).model_dump_json()
                    )
                if emit_event_batch:
                    await websocket.send_text(
                        EventBatch(
                            request_id=f"events-{packet.sequence}",
                            scene_id=capture.scene_id,
                            sequence=packet.sequence,
                            events=result.events,
                        ).model_dump_json()
                    )
                await websocket.send_text(result.model_dump_json())
                last_captured_at = packet.captured_at
                last_sequence = packet.sequence
            except WebSocketDisconnect:
                break
            except FrameProtocolError as error:
                await _send_error(
                    websocket,
                    code="invalid_frame",
                    message=str(error),
                    request_id=f"frame-{last_sequence + 1}",
                )
            except Exception:
                failed = True
                await _send_error(
                    websocket,
                    code="inference_failed",
                    message="The local perception worker failed for this frame.",
                    request_id=f"frame-{last_sequence + 1}",
                    recoverable=False,
                )
                await websocket.close(code=4500)
                break
            finally:
                _ = (perf_counter() - started) * 1000.0
    except (TimeoutError, ValueError, ValidationError):
        failed = True
        await _send_error(
            websocket,
            code="invalid_hello",
            message="The initial protocol handshake is invalid.",
            recoverable=False,
        )
        await websocket.close(code=4400)
    except WebSocketDisconnect:
        pass
    finally:
        if pending_checkpoint is not None:
            try:
                await asyncio.wait_for(asyncio.shield(pending_checkpoint), timeout=30.0)
            except Exception:
                failed = True
        if provider is not None:
            await asyncio.to_thread(services.providers.release, provider)
        if scheduler_owned:
            services.scheduler.stop_live()
        if capture_session_id is not None:
            services.repository.finish_capture_session(
                capture_session_id,
                status="failed" if failed else "completed",
            )


async def _handle_command(
    websocket: WebSocket,
    *,
    text: str,
    services: AppServices,
    cache: dict[str, CommandResult],
) -> None:
    try:
        command = CommandSubmit.model_validate_json(text)
    except ValidationError:
        await _send_error(
            websocket,
            code="invalid_command",
            message="The command does not match protocol v1.",
        )
        return
    cached = cache.get(command.idempotency_key)
    if cached is not None:
        await websocket.send_text(cached.model_dump_json())
        return
    if services.repository.get_scene(command.scene_id) is None:
        result = CommandResult(
            request_id=command.request_id,
            idempotency_key=command.idempotency_key,
            status="rejected",
            result={"code": "scene_not_found"},
        )
    elif (
        command.entity_id is not None and services.repository.get_entity(command.entity_id) is None
    ):
        result = CommandResult(
            request_id=command.request_id,
            idempotency_key=command.idempotency_key,
            status="rejected",
            result={"code": "entity_not_found"},
        )
    elif command.entity_id is not None and command.expected_entity_state_id is not None:
        current_state = services.repository.get_current_state(command.entity_id)
        if current_state is None or current_state.id != command.expected_entity_state_id:
            result = CommandResult(
                request_id=command.request_id,
                idempotency_key=command.idempotency_key,
                status="rejected",
                result={"code": "entity_version_conflict"},
            )
        else:
            result = CommandResult(
                request_id=command.request_id,
                idempotency_key=command.idempotency_key,
                status="completed",
                result={"accepted_by": "worldstate-backend"},
            )
    elif command.command.value == "cancel_job":
        job_id = command.arguments.get("job_id")
        job = services.jobs.cancel(str(job_id)) if job_id else None
        result = CommandResult(
            request_id=command.request_id,
            idempotency_key=command.idempotency_key,
            status="completed" if job is not None else "rejected",
            result={"job_id": job.id, "status": job.status} if job else {"code": "job_not_found"},
        )
    elif command.command.value == "start_scan":
        artifact_id = command.arguments.get("video_artifact_id")
        session_id = command.arguments.get("session_id")
        try:
            job = services.jobs.submit(
                kind="scan",
                scene_id=command.scene_id,
                session_id=str(session_id) if session_id else None,
                parameters={"video_artifact_id": artifact_id},
            )
            result = CommandResult(
                request_id=command.request_id,
                idempotency_key=command.idempotency_key,
                status="accepted",
                result={"job_id": job.id},
            )
        except (JobQueueFull, ValueError):
            result = CommandResult(
                request_id=command.request_id,
                idempotency_key=command.idempotency_key,
                status="rejected",
                result={"code": "scan_not_started"},
            )
    elif command.command.value in {"query_entity", "find_last_seen"} and command.entity_id:
        entity = services.repository.get_entity(command.entity_id)
        state = services.repository.get_current_state(command.entity_id)
        result = CommandResult(
            request_id=command.request_id,
            idempotency_key=command.idempotency_key,
            status="completed",
            result={
                "entity_id": command.entity_id,
                "label": entity.display_name if entity else None,
                "last_seen_at": (
                    entity.last_seen_at.isoformat() if entity and entity.last_seen_at else None
                ),
                "position_m": state.position_m if state else None,
                "confidence": state.confidence if state else 0.0,
            },
        )
    else:
        result = CommandResult(
            request_id=command.request_id,
            idempotency_key=command.idempotency_key,
            status="completed",
            result={"accepted_by": "worldstate-backend"},
        )
    if len(cache) >= 256:
        cache.pop(next(iter(cache)))
    cache[command.idempotency_key] = result
    await websocket.send_text(result.model_dump_json())
