from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import Any

import cv2
import numpy as np
import pytest
from conftest import ORIGIN, AuthenticatedClient
from starlette.websockets import WebSocketDisconnect

from worldstate_api.capture import FramePacket, pack_frame


def _frame(sequence: int, *, captured_at: datetime | None = None) -> bytes:
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    image[8:32, 12:40] = (40, 120, 220)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return pack_frame(
        FramePacket(
            sequence=sequence,
            captured_at=captured_at or datetime.now(UTC),
            width=64,
            height=48,
            encoding="jpeg",
            payload=encoded.tobytes(),
        )
    )


def test_websocket_handshake_frame_ack_ordering_and_idempotent_commands(
    app_client: AuthenticatedClient,
) -> None:
    scene = app_client.client.post(
        "/api/v1/scenes",
        headers=app_client.mutation_headers,
        json={"name": "Live Desk", "object_prompts": ["cup", "book"]},
    ).json()
    capture = app_client.client.post(
        f"/api/v1/scenes/{scene['id']}/sessions",
        headers=app_client.mutation_headers,
        json={"mode": "replay", "source_name": "synthetic-desk"},
    ).json()

    with app_client.client.websocket_connect(
        "/api/v1/live",
        headers={"Origin": ORIGIN},
    ) as websocket:
        websocket.send_json(
            {
                "type": "client.hello",
                "protocol_version": "v1",
                "request_id": "hello-1",
                "session_id": capture["id"],
                "prompts": ["cup", "book"],
            }
        )
        ready = websocket.receive_json()
        assert ready["type"] == "server.ready"
        assert ready["provider_mode"] == "replay"

        websocket.send_bytes(_frame(1))
        patch = websocket.receive_json()
        event_batch = websocket.receive_json()
        frame = websocket.receive_json()
        assert patch["type"] == "world.patch"
        assert event_batch["type"] == "event.batch"
        assert frame["type"] == "frame.result"
        assert frame["sequence"] == 1
        assert len(frame["objects"]) == 2
        assert frame["metrics"]["queue_depth"] == 0

        websocket.send_bytes(_frame(1))
        rejected = websocket.receive_json()
        assert rejected["type"] == "error"
        assert rejected["code"] == "invalid_frame"
        assert "monotonically" in rejected["message"]

        command: dict[str, Any] = {
            "type": "command.submit",
            "protocol_version": "v1",
            "request_id": "command-1",
            "idempotency_key": "stable-idempotency-key-0001",
            "command": "select_entity",
            "scene_id": scene["id"],
            "entity_id": frame["objects"][0]["entity_id"],
            "arguments": {},
        }
        websocket.send_json(command)
        first = websocket.receive_json()
        websocket.send_json(command)
        second = websocket.receive_json()
        assert first == second
        assert first["status"] == "completed"

        conflict: dict[str, Any] = {
            **command,
            "request_id": "command-2",
            "idempotency_key": "stable-idempotency-key-0002",
            "expected_entity_state_id": "018f0000-0000-7000-8000-000000000099",
        }
        websocket.send_json(conflict)
        rejected_version = websocket.receive_json()
        assert rejected_version["status"] == "rejected"
        assert rejected_version["result"]["code"] == "entity_version_conflict"
        websocket.close()

    deadline = time.monotonic() + 2
    finished = app_client.client.get(f"/api/v1/sessions/{capture['id']}").json()
    while finished["status"] == "active" and time.monotonic() < deadline:
        time.sleep(0.01)
        finished = app_client.client.get(f"/api/v1/sessions/{capture['id']}").json()
    assert finished["status"] == "completed"


def test_websocket_rejects_missing_browser_session(app_client: AuthenticatedClient) -> None:
    from fastapi.testclient import TestClient

    fresh = TestClient(app_client.app)
    with (
        pytest.raises(WebSocketDisconnect) as rejected,
        fresh.websocket_connect(
            "/api/v1/live",
            headers={"Origin": ORIGIN},
        ),
    ):
        raise AssertionError("unauthenticated websocket was accepted")
    assert rejected.value.code == 4403


def test_live_frames_render_immediately_but_checkpoint_history_within_one_second(
    app_client: AuthenticatedClient,
) -> None:
    scene = app_client.client.post(
        "/api/v1/scenes",
        headers=app_client.mutation_headers,
        json={"name": "Cadence Desk", "object_prompts": ["cup"]},
    ).json()
    capture = app_client.client.post(
        f"/api/v1/scenes/{scene['id']}/sessions",
        headers=app_client.mutation_headers,
        json={"mode": "replay", "source_name": "synthetic-desk"},
    ).json()
    captured_at = datetime.now(UTC)

    with app_client.client.websocket_connect(
        "/api/v1/live",
        headers={"Origin": ORIGIN},
    ) as websocket:
        websocket.send_json(
            {
                "type": "client.hello",
                "protocol_version": "v1",
                "request_id": "hello-cadence",
                "session_id": capture["id"],
                "prompts": ["cup"],
            }
        )
        assert websocket.receive_json()["type"] == "server.ready"
        entity_id = ""
        for sequence, offset_ms in ((1, 0), (2, 400), (3, 800)):
            websocket.send_bytes(
                _frame(sequence, captured_at=captured_at + timedelta(milliseconds=offset_ms))
            )
            assert websocket.receive_json()["type"] == "world.patch"
            assert websocket.receive_json()["type"] == "event.batch"
            result = websocket.receive_json()
            assert result["type"] == "frame.result"
            entity_id = result["objects"][0]["entity_id"]

    states = app_client.app.state.services.repository.list_entity_states(entity_id)
    assert len(states) == 2


def test_slow_durable_checkpoint_does_not_block_live_frame_results(
    app_client: AuthenticatedClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene = app_client.client.post(
        "/api/v1/scenes",
        headers=app_client.mutation_headers,
        json={"name": "Write-behind Desk", "object_prompts": ["cup"]},
    ).json()
    capture = app_client.client.post(
        f"/api/v1/scenes/{scene['id']}/sessions",
        headers=app_client.mutation_headers,
        json={"mode": "replay", "source_name": "synthetic-desk"},
    ).json()
    engine = app_client.app.state.services.world_engine
    original_process = engine.process
    checkpoint_started = Event()
    process_calls = 0

    def delayed_process(**kwargs: object) -> object:
        nonlocal process_calls
        process_calls += 1
        if process_calls > 1:
            checkpoint_started.set()
            time.sleep(0.5)
        return original_process(**kwargs)

    monkeypatch.setattr(engine, "process", delayed_process)
    captured_at = datetime.now(UTC)
    with app_client.client.websocket_connect(
        "/api/v1/live",
        headers={"Origin": ORIGIN},
    ) as websocket:
        websocket.send_json(
            {
                "type": "client.hello",
                "protocol_version": "v1",
                "request_id": "hello-write-behind",
                "session_id": capture["id"],
                "prompts": ["cup"],
                "requested_capabilities": ["frame.result"],
            }
        )
        ready = websocket.receive_json()
        assert ready["type"] == "server.ready"
        assert ready["accepted_capabilities"] == ["frame.result"]
        for sequence, offset_ms in ((1, 0), (2, 800)):
            websocket.send_bytes(
                _frame(sequence, captured_at=captured_at + timedelta(milliseconds=offset_ms))
            )
            assert websocket.receive_json()["type"] == "frame.result"

        assert checkpoint_started.wait(timeout=0.2)
        started = time.perf_counter()
        websocket.send_bytes(_frame(3, captured_at=captured_at + timedelta(milliseconds=900)))
        assert websocket.receive_json()["type"] == "frame.result"
        assert time.perf_counter() - started < 0.25
