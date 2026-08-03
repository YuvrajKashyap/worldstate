# pyright: basic
"""Exercise the compiled same-origin product against a running backend."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np
from websockets.sync.client import connect

from worldstate_api.capture import FramePacket, pack_frame


def _frame(sequence: int) -> bytes:
    image = np.full((360, 640, 3), 235, dtype=np.uint8)
    cv2.rectangle(image, (70, 145), (180, 290), (30, 70, 180), thickness=-1)
    cv2.rectangle(image, (245, 185), (430, 285), (50, 150, 60), thickness=-1)
    cv2.circle(image, (520, 215), 58, (180, 80, 35), thickness=-1)
    encoded, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not encoded:
        raise RuntimeError("could not encode the smoke frame")
    return pack_frame(
        FramePacket(
            sequence=sequence,
            captured_at=datetime.now(UTC),
            width=640,
            height=360,
            encoding="jpeg",
            payload=jpeg.tobytes(),
        )
    )


def _receive_frame_result(websocket: Any) -> dict[str, object]:
    messages: list[dict[str, object]] = []
    for _ in range(3):
        raw = websocket.recv(timeout=30)
        if not isinstance(raw, str):
            raise RuntimeError("the backend returned an unexpected binary response")
        messages.append(json.loads(raw))
    by_type = {str(message.get("type")): message for message in messages}
    if set(by_type) != {"world.patch", "event.batch", "frame.result"}:
        raise RuntimeError(f"unexpected live response family: {sorted(by_type)}")
    return by_type["frame.result"]


def _write_scan_video(path: Path) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),  # type: ignore[attr-defined]
        1.0,
        (640, 360),
    )
    if not writer.isOpened():
        raise RuntimeError("could not create the scan smoke video")
    generator = np.random.default_rng(20260730)
    try:
        for index in range(2):
            image = generator.integers(0, 256, (360, 640, 3), dtype=np.uint8)
            cv2.putText(
                image,
                f"WorldState scan view {index + 1}",
                (85, 180),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.1,
                (255, 255, 255),
                3,
                cv2.LINE_AA,
            )
            writer.write(image)
    finally:
        writer.release()


def _run_scan(
    client: httpx.Client,
    *,
    scene_id: str,
    mutation_headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, object]:
    capture = client.post(
        f"/api/v1/scenes/{scene_id}/sessions",
        headers=mutation_headers,
        json={"mode": "scan", "source_name": "synthetic-two-view.mp4"},
    )
    capture.raise_for_status()
    session_id = str(capture.json()["id"])
    with tempfile.TemporaryDirectory(prefix="worldstate-production-scan-") as directory:
        video_path = Path(directory) / "scan.mp4"
        _write_scan_video(video_path)
        with video_path.open("rb") as source:
            upload = client.post(
                f"/api/v1/sessions/{session_id}/video",
                headers=mutation_headers,
                files={"upload": ("scan.mp4", source, "video/mp4")},
            )
    upload.raise_for_status()
    artifact_id = str(upload.json()["artifact_id"])
    submitted = client.post(
        "/api/v1/jobs",
        headers=mutation_headers,
        json={
            "kind": "scan",
            "scene_id": scene_id,
            "session_id": session_id,
            "parameters": {"video_artifact_id": artifact_id},
        },
    )
    submitted.raise_for_status()
    job_id = str(submitted.json()["id"])
    deadline = time.monotonic() + timeout_seconds
    job: dict[str, object] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}", timeout=60)
        response.raise_for_status()
        job = response.json()
        if job.get("status") in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(2)
    if job.get("status") != "succeeded":
        raise RuntimeError(
            f"scan smoke did not succeed: {job.get('status')} / {job.get('error_code')}"
        )
    result = job.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("scan smoke returned no result")
    geometry_ids = result.get("geometry_artifact_ids")
    if not isinstance(geometry_ids, list) or not geometry_ids:
        raise RuntimeError("scan smoke returned no geometry artifacts")
    return {
        "job_id": job_id,
        "result_status": result.get("status"),
        "geometry_artifact_count": len(geometry_ids),
        "keyframe_count": result.get("keyframe_count"),
        "approximate_scale": result.get("approximate_scale"),
    }


def run(
    base_url: str,
    token: str,
    *,
    include_scan: bool = False,
    scan_timeout_seconds: float = 900.0,
) -> dict[str, object]:
    origin = base_url.rstrip("/")
    websocket_url = origin.replace("http://", "ws://", 1) + "/api/v1/live"
    with httpx.Client(
        base_url=origin,
        timeout=30.0,
        headers={"Origin": origin},
    ) as client:
        root = client.get("/")
        root.raise_for_status()
        if "WorldState" not in root.text:
            raise RuntimeError("compiled frontend was not served from the backend")
        csp = root.headers.get("content-security-policy", "")
        if "'wasm-unsafe-eval'" not in csp:
            raise RuntimeError("production CSP does not permit the local MediaPipe WASM runtime")
        model = client.head("/models/hand_landmarker.task")
        model.raise_for_status()
        if int(model.headers.get("content-length", "0")) < 1_000_000:
            raise RuntimeError("the local hand landmark model is missing or unexpectedly small")

        bootstrap = client.post("/api/v1/bootstrap", json={"token": token})
        bootstrap.raise_for_status()
        csrf = str(bootstrap.json()["csrf_token"])
        mutation_headers = {"X-WorldState-CSRF": csrf}
        system = client.get("/api/v1/system")
        system.raise_for_status()
        system_payload = system.json()
        if system_payload["provider_mode"] != "models":
            raise RuntimeError("production is not using the learned provider")
        if system_payload["capabilities"]["live_learned"] != "ready":
            raise RuntimeError("the learned provider capability is not ready")

        scene = client.post(
            "/api/v1/scenes",
            headers=mutation_headers,
            json={
                "name": "Production smoke",
                "object_prompts": ["cup", "book", "phone"],
            },
        )
        scene.raise_for_status()
        scene_id = str(scene.json()["id"])
        cookie = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
        frame_latencies: list[float] = []
        observations: list[int] = []
        scan_report: dict[str, object] | None = None
        try:
            session_count = 3 if include_scan else 2
            for session_number in range(session_count):
                if include_scan and session_number == 2:
                    scan_report = _run_scan(
                        client,
                        scene_id=scene_id,
                        mutation_headers=mutation_headers,
                        timeout_seconds=scan_timeout_seconds,
                    )
                capture = client.post(
                    f"/api/v1/scenes/{scene_id}/sessions",
                    headers=mutation_headers,
                    json={"mode": "live", "source_name": f"smoke-{session_number}"},
                )
                capture.raise_for_status()
                session_id = str(capture.json()["id"])
                with connect(
                    websocket_url,
                    origin=origin,  # type: ignore[arg-type]
                    additional_headers={"Cookie": cookie},
                    max_size=8_000_000,
                ) as websocket:
                    websocket.send(
                        json.dumps(
                            {
                                "type": "client.hello",
                                "protocol_version": "v1",
                                "request_id": f"hello-{session_number}",
                                "session_id": session_id,
                                "prompts": ["cup", "book", "phone"],
                            }
                        )
                    )
                    ready = json.loads(websocket.recv(timeout=10))
                    if ready.get("type") != "server.ready":
                        raise RuntimeError("live handshake did not become ready")
                    started = time.perf_counter()
                    websocket.send(_frame(1))
                    result = _receive_frame_result(websocket)
                    frame_latencies.append((time.perf_counter() - started) * 1000.0)
                    objects = result.get("objects")
                    observations.append(len(objects) if isinstance(objects, list) else 0)
        finally:
            deletion = client.delete(
                f"/api/v1/scenes/{scene_id}",
                headers=mutation_headers,
            )
            deletion.raise_for_status()

    return {
        "status": "passed",
        "scope": "compiled same-origin frontend, security bootstrap, local gesture asset, "
        "persistent learned worker, and repeated live WebSocket sessions",
        "provider_mode": system_payload["provider_mode"],
        "frame_round_trip_ms": frame_latencies,
        "observation_counts": observations,
        "csp_local_wasm": True,
        "hand_model_bytes": int(model.headers["content-length"]),
        "scan": scan_report,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", required=True)
    parser.add_argument("--include-scan", action="store_true")
    parser.add_argument("--scan-timeout-seconds", type=float, default=900.0)
    arguments = parser.parse_args()
    print(
        json.dumps(
            run(
                arguments.base_url,
                arguments.token,
                include_scan=arguments.include_scan,
                scan_timeout_seconds=arguments.scan_timeout_seconds,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
