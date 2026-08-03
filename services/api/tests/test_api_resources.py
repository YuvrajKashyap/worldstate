from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime

from conftest import ORIGIN, AuthenticatedClient
from fastapi.testclient import TestClient


def _create_scene(auth: AuthenticatedClient, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Desk",
        "description": "Local test scene",
        "persistence_enabled": False,
        "object_prompts": ["cup", "book"],
    }
    payload.update(overrides)
    response = auth.client.post(
        "/api/v1/scenes",
        headers=auth.mutation_headers,
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_bootstrap_is_one_time_and_produces_hardened_cookie(
    app_client: AuthenticatedClient,
) -> None:
    client, app, _headers = app_client
    response = client.post(
        "/api/v1/bootstrap",
        headers={"Origin": ORIGIN},
        json={"token": app.state.services.sessions.launcher_token},
    )

    assert response.status_code == 401
    assert "worldstate_session" in client.cookies


def test_same_origin_session_refresh_restores_csrf_capability(
    app_client: AuthenticatedClient,
) -> None:
    response = app_client.client.post(
        "/api/v1/session/refresh",
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 200
    assert response.json()["csrf_token"] == app_client.mutation_headers["X-WorldState-CSRF"]
    assert response.headers["Cache-Control"] == "no-store"

    rejected = app_client.client.post(
        "/api/v1/session/refresh",
        headers={"Origin": "https://attacker.example"},
    )
    assert rejected.status_code == 403


def test_auth_origin_csrf_and_unknown_field_boundaries(
    app_client: AuthenticatedClient,
) -> None:
    client, _app, headers = app_client

    fresh = TestClient(_app)
    assert fresh.get("/api/v1/scenes").status_code == 401
    assert client.post("/api/v1/scenes", json={"name": "x"}).status_code == 403
    assert (
        client.post(
            "/api/v1/scenes",
            headers={"Origin": ORIGIN},
            json={"name": "x"},
        ).status_code
        == 403
    )
    response = client.post(
        "/api/v1/scenes",
        headers=headers,
        json={"name": "x", "unknown": True},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_scene_crud_prompt_policy_and_security_headers(
    app_client: AuthenticatedClient,
) -> None:
    scene = _create_scene(app_client)
    scene_id = str(scene["id"])

    fetched = app_client.client.get(f"/api/v1/scenes/{scene_id}")
    assert fetched.status_code == 200
    assert fetched.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in fetched.headers["Content-Security-Policy"]
    assert fetched.json()["coordinate_frame"] == "worldstate_scene_v1"

    patched = app_client.client.patch(
        f"/api/v1/scenes/{scene_id}",
        headers=app_client.mutation_headers,
        json={"name": "Updated Desk", "description": None},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Updated Desk"
    assert patched.json()["description"] is None

    policy = app_client.client.patch(
        f"/api/v1/scenes/{scene_id}",
        headers=app_client.mutation_headers,
        json={"object_prompts": ["infer race"]},
    )
    assert policy.status_code == 422
    assert policy.json()["error"]["code"] == "prompt_policy"

    listed = app_client.client.get("/api/v1/scenes")
    assert len(listed.json()["items"]) == 1
    assert (
        app_client.client.delete(
            f"/api/v1/scenes/{scene_id}",
            headers=app_client.mutation_headers,
        ).status_code
        == 204
    )
    assert app_client.client.get(f"/api/v1/scenes/{scene_id}").status_code == 404


def test_capture_and_temporal_memory_resources(app_client: AuthenticatedClient) -> None:
    scene_id = str(_create_scene(app_client)["id"])
    created = app_client.client.post(
        f"/api/v1/scenes/{scene_id}/sessions",
        headers=app_client.mutation_headers,
        json={
            "mode": "replay",
            "source_name": "synthetic-desk",
            "camera": {"width": 640, "height": 360, "fx": 500, "fy": 500},
        },
    )
    assert created.status_code == 201
    session_id = created.json()["id"]
    assert app_client.client.get(f"/api/v1/sessions/{session_id}").status_code == 200
    finished = app_client.client.post(
        f"/api/v1/sessions/{session_id}/finish",
        headers=app_client.mutation_headers,
    )
    assert finished.json()["status"] == "completed"

    repository = app_client.app.state.services.repository
    at = datetime.now(UTC)
    entity = repository.create_entity(
        scene_id=scene_id,
        label="cup",
        layer="persistent",
        observed_at=at,
    )
    repository.append_entity_state(
        entity_id=entity.id,
        valid_from=at,
        presence="visible",
        confidence=0.91,
        uncertainty=0.09,
        position_m=(0.1, 0.2, 1.0),
        quaternion_xyzw=None,
        bounds_m=(0.1, 0.1, 0.2),
        box_xyxy=(1, 2, 3, 4),
        evidence_ids=(),
    )
    repository.create_event(
        scene_id=scene_id,
        entity_id=entity.id,
        kind="added",
        occurred_at=at,
        confidence=0.91,
        evidence_ids=(),
    )

    entities = app_client.client.get(f"/api/v1/scenes/{scene_id}/entities?label=cup")
    history = app_client.client.get(f"/api/v1/entities/{entity.id}")
    last_seen = app_client.client.get(f"/api/v1/entities/{entity.id}/last-seen")
    events = app_client.client.get(f"/api/v1/scenes/{scene_id}/events")
    snapshot = app_client.client.get(
        f"/api/v1/scenes/{scene_id}/snapshot",
        params={"at": at.isoformat()},
    )

    assert entities.json()["items"][0]["canonical_label"] == "cup"
    assert len(history.json()["states"]) == 1
    assert last_seen.json()["position_m"] == [0.1, 0.2, 1.0]
    assert events.json()["items"][0]["kind"] == "added"
    assert snapshot.json()["entities"][0]["id"] == entity.id


def test_capture_modes_are_isolated_from_webcam_and_replay_scenes(
    app_client: AuthenticatedClient,
) -> None:
    persistent = _create_scene(
        app_client,
        name="Live Desk",
        persistence_enabled=True,
    )
    synthetic = _create_scene(
        app_client,
        name="Synthetic Desk",
        persistence_enabled=False,
    )

    wrong_live_source = app_client.client.post(
        f"/api/v1/scenes/{persistent['id']}/sessions",
        headers=app_client.mutation_headers,
        json={"mode": "live", "source_name": "synthetic-desk"},
    )
    assert wrong_live_source.status_code == 409

    replay_into_persistent = app_client.client.post(
        f"/api/v1/scenes/{persistent['id']}/sessions",
        headers=app_client.mutation_headers,
        json={"mode": "replay", "source_name": "synthetic-desk"},
    )
    assert replay_into_persistent.status_code == 409

    webcam_with_replay_provider = app_client.client.post(
        f"/api/v1/scenes/{persistent['id']}/sessions",
        headers=app_client.mutation_headers,
        json={"mode": "live", "source_name": "browser-webcam"},
    )
    assert webcam_with_replay_provider.status_code == 409

    replay = app_client.client.post(
        f"/api/v1/scenes/{synthetic['id']}/sessions",
        headers=app_client.mutation_headers,
        json={"mode": "replay", "source_name": "synthetic-desk"},
    )
    assert replay.status_code == 201

    app_client.app.state.services.settings.provider_mode = "models"
    webcam = app_client.client.post(
        f"/api/v1/scenes/{persistent['id']}/sessions",
        headers=app_client.mutation_headers,
        json={"mode": "live", "source_name": "browser-webcam"},
    )
    assert webcam.status_code == 201


def test_video_upload_type_sniffing_and_artifact_download(
    app_client: AuthenticatedClient,
) -> None:
    scene_id = str(_create_scene(app_client)["id"])
    capture = app_client.client.post(
        f"/api/v1/scenes/{scene_id}/sessions",
        headers=app_client.mutation_headers,
        json={"mode": "scan", "source_name": "phone.mov"},
    ).json()
    session_id = capture["id"]

    invalid = app_client.client.post(
        f"/api/v1/sessions/{session_id}/video",
        headers=app_client.mutation_headers,
        files={"upload": ("bad.mp4", b"not-video", "video/mp4")},
    )
    assert invalid.status_code == 415

    media = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32
    uploaded = app_client.client.post(
        f"/api/v1/sessions/{session_id}/video",
        headers=app_client.mutation_headers,
        files={"upload": ("desk.mp4", media, "video/mp4")},
    )
    assert uploaded.status_code == 201
    artifact_id = uploaded.json()["artifact_id"]
    downloaded = app_client.client.get(f"/api/v1/artifacts/{artifact_id}")
    assert downloaded.content == media
    assert downloaded.headers["Cache-Control"] == "private, no-store"
    deleted = app_client.client.delete(
        f"/api/v1/scenes/{scene_id}",
        headers=app_client.mutation_headers,
    )
    assert deleted.status_code == 204
    assert app_client.client.get(f"/api/v1/artifacts/{artifact_id}").status_code == 404


def test_system_diagnostics_models_storage_replays_and_gc(
    app_client: AuthenticatedClient,
) -> None:
    for path in (
        "/api/v1/system",
        "/api/v1/diagnostics",
        "/api/v1/models",
        "/api/v1/storage",
        "/api/v1/replays",
    ):
        response = app_client.client.get(path)
        assert response.status_code == 200, path

    stored = app_client.app.state.services.artifacts.put_bytes(
        b"orphan",
        media_type="application/octet-stream",
        kind="test",
    )
    assert stored.size_bytes == 6
    collected = app_client.client.post(
        "/api/v1/storage/garbage-collect",
        headers=app_client.mutation_headers,
    )
    assert collected.json() == {"removed_artifacts": 1, "reclaimed_bytes": 6}


def test_checksum_verified_hand_model_is_served_from_the_local_registry(
    app_client: AuthenticatedClient,
) -> None:
    services = app_client.app.state.services
    spec = services.model_registry.get_spec("mediapipe-hand-landmarker")
    model_root = services.settings.models_root / spec.relative_path
    model_root.mkdir(parents=True)
    payload = b"local-hand-model"
    (model_root / "hand_landmarker.task").write_bytes(payload)
    services.settings.model_lock_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "models": {
                    spec.id: {
                        "revision": spec.revision,
                        "files": {
                            "hand_landmarker.task": hashlib.sha256(payload).hexdigest(),
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    response = app_client.client.get("/models/hand_landmarker.task")
    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["cache-control"] == "private, max-age=31536000, immutable"


def test_evaluation_job_runs_persistently(app_client: AuthenticatedClient) -> None:
    manifest = {
        "schema_version": 1,
        "event_counts": {"true_positives": 9, "false_positives": 1, "false_negatives": 1},
        "confidences": [0.9],
        "outcomes": [True],
        "latency_ms": [50],
    }
    import json

    artifact = app_client.app.state.services.artifacts.put_bytes(
        json.dumps(manifest).encode(),
        media_type="application/json",
        kind="evaluation-manifest",
        ref_count=1,
    )
    created = app_client.client.post(
        "/api/v1/jobs",
        headers=app_client.mutation_headers,
        json={
            "kind": "evaluation",
            "parameters": {"manifest_artifact_id": artifact.id, "seed": 7},
        },
    )
    assert created.status_code == 202
    job_id = created.json()["id"]

    deadline = time.monotonic() + 5
    status = "queued"
    result: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = app_client.client.get(f"/api/v1/jobs/{job_id}")
        status = response.json()["status"]
        result = response.json()
        if status in {"succeeded", "failed"}:
            break
        time.sleep(0.01)

    assert status == "succeeded"
    assert result["result"]["result_artifact_id"]
    assert app_client.client.get("/api/v1/jobs").json()["items"]


def test_scene_export_job_produces_authorized_manifest(
    app_client: AuthenticatedClient,
) -> None:
    scene_id = str(_create_scene(app_client)["id"])
    created = app_client.client.post(
        "/api/v1/jobs",
        headers=app_client.mutation_headers,
        json={
            "kind": "export",
            "scene_id": scene_id,
            "parameters": {"formats": ["manifest"]},
        },
    )
    assert created.status_code == 202
    job_id = created.json()["id"]

    deadline = time.monotonic() + 5
    result = created.json()
    while time.monotonic() < deadline:
        result = app_client.client.get(f"/api/v1/jobs/{job_id}").json()
        if result["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.01)

    assert result["status"] == "succeeded"
    artifact_id = result["result"]["artifact_ids"][0]
    downloaded = app_client.client.get(f"/api/v1/artifacts/{artifact_id}")
    assert downloaded.status_code == 200
    assert downloaded.json()["scene"]["id"] == scene_id


def test_logout_revokes_session(app_client: AuthenticatedClient) -> None:
    response = app_client.client.post(
        "/api/v1/session/logout",
        headers=app_client.mutation_headers,
    )
    assert response.status_code == 204
    assert app_client.client.get("/api/v1/scenes").status_code == 401
