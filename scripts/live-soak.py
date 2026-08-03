# pyright: basic
"""Run an acknowledgement-paced learned-provider stability soak."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import httpx
import numpy as np
from websockets.sync.client import connect

from worldstate_api.capture import FramePacket, pack_frame
from worldstate_api.providers.registry import ModelRegistry
from worldstate_api.settings import Settings


def _encoded_frame(sequence: int) -> tuple[bytes, int]:
    image = np.full((360, 640, 3), 235, dtype=np.uint8)
    cv2.rectangle(image, (70, 145), (180, 290), (30, 70, 180), thickness=-1)
    cv2.rectangle(image, (245, 185), (430, 285), (50, 150, 60), thickness=-1)
    cv2.circle(image, (520, 215), 58, (180, 80, 35), thickness=-1)
    shift_x = round(28.0 * np.sin(sequence * 0.08))
    if shift_x:
        image = cv2.warpAffine(
            image,
            np.asarray([[1.0, 0.0, float(shift_x)], [0.0, 1.0, 0.0]]),
            (640, 360),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(235, 235, 235),
        )
    encoded, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not encoded:
        raise RuntimeError("could not encode the soak frame")
    return jpeg.tobytes(), shift_x


def _centers_by_label(objects: object) -> dict[str, tuple[float, float]]:
    if not isinstance(objects, list):
        return {}
    centers: dict[str, tuple[float, float]] = {}
    for item in objects:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        box = item.get("box_xyxy")
        if not isinstance(label, str) or not isinstance(box, list) or len(box) != 4:
            continue
        centers.setdefault(
            label,
            ((float(box[0]) + float(box[2])) / 2.0, (float(box[1]) + float(box[3])) / 2.0),
        )
    return centers


def _packet(payload: bytes, sequence: int) -> bytes:
    return pack_frame(
        FramePacket(
            sequence=sequence,
            captured_at=datetime.now(UTC),
            width=640,
            height=360,
            encoding="jpeg",
            payload=payload,
        )
    )


def _receive_result(websocket: Any) -> dict[str, object]:
    result: dict[str, object] | None = None
    for _ in range(3):
        raw = websocket.recv(timeout=30)
        if not isinstance(raw, str):
            raise RuntimeError("unexpected binary response")
        message = json.loads(raw)
        if message.get("type") == "frame.result":
            result = message
    if result is None:
        raise RuntimeError("frame.result was not returned")
    return result


def _slope_per_minute(samples: list[tuple[float, float]]) -> float:
    if len(samples) < 2:
        return 0.0
    times = np.asarray([sample[0] for sample in samples], dtype=np.float64) / 60.0
    values = np.asarray([sample[1] for sample in samples], dtype=np.float64)
    return float(np.polyfit(times, values, 1)[0])


def _number(mapping: dict[str, object], key: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, int | float):
        raise RuntimeError(f"diagnostics field {key} is not numeric")
    return float(value)


def _provenance() -> dict[str, object]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
        )
    except (OSError, subprocess.SubprocessError):
        revision = "unknown"
        dirty = True
    lock_path = Settings().model_lock_path
    lock_hash = ModelRegistry.hash_file(lock_path) if lock_path.is_file() else "not_available"
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_revision": revision,
        "dirty_worktree": dirty,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "model_lock_sha256": lock_hash,
    }


def run(
    *,
    base_url: str,
    token: str,
    duration_seconds: int,
    target_fps: float,
) -> dict[str, object]:
    origin = base_url.rstrip("/")
    websocket_url = origin.replace("http://", "ws://", 1) + "/api/v1/live"
    with httpx.Client(
        base_url=origin,
        timeout=30,
        headers={"Origin": origin},
    ) as client:
        bootstrap = client.post("/api/v1/bootstrap", json={"token": token})
        bootstrap.raise_for_status()
        csrf = str(bootstrap.json()["csrf_token"])
        mutation_headers = {"X-WorldState-CSRF": csrf}
        scene = client.post(
            "/api/v1/scenes",
            headers=mutation_headers,
            json={
                "name": "Live stability soak",
                "object_prompts": ["cup", "book", "phone"],
            },
        )
        scene.raise_for_status()
        scene_id = str(scene.json()["id"])
        cookie = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
        latencies_ms: list[float] = []
        provider_latencies_ms: list[float] = []
        worker_gpu_allocated: list[tuple[float, float]] = []
        worker_gpu_reserved: list[tuple[float, float]] = []
        diagnostic_samples: list[dict[str, object]] = []
        object_counts: list[int] = []
        baseline_centers: dict[str, tuple[float, float]] | None = None
        baseline_shift = 0
        center_errors_px: list[float] = []
        identity_coverages: list[float] = []
        started = time.monotonic()
        next_diagnostic = started
        next_frame = started
        sequence = 0
        capture_elapsed = 0.0
        capture_error: BaseException | None = None
        try:
            capture = client.post(
                f"/api/v1/scenes/{scene_id}/sessions",
                headers=mutation_headers,
                json={"mode": "live", "source_name": "dynamic-live-soak"},
            )
            capture.raise_for_status()
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
                            "request_id": "soak-hello",
                            "session_id": capture.json()["id"],
                            "prompts": ["cup", "book", "phone"],
                        }
                    )
                )
                ready = json.loads(websocket.recv(timeout=10))
                if ready.get("type") != "server.ready":
                    raise RuntimeError("soak live session did not become ready")
                while time.monotonic() - started < duration_seconds:
                    now = time.monotonic()
                    if now < next_frame:
                        time.sleep(min(next_frame - now, 0.02))
                        continue
                    sequence += 1
                    payload, shift_x = _encoded_frame(sequence)
                    frame_started = time.perf_counter()
                    websocket.send(_packet(payload, sequence))
                    result = _receive_result(websocket)
                    latencies_ms.append((time.perf_counter() - frame_started) * 1000.0)
                    metrics = result.get("metrics")
                    if isinstance(metrics, dict):
                        provider_latencies_ms.append(float(metrics.get("inference_ms", 0.0)))
                        sampled_at = time.monotonic() - started
                        allocated = metrics.get("gpu_allocated_bytes")
                        reserved = metrics.get("gpu_reserved_bytes")
                        if isinstance(allocated, int | float):
                            worker_gpu_allocated.append((sampled_at, float(allocated)))
                        if isinstance(reserved, int | float):
                            worker_gpu_reserved.append((sampled_at, float(reserved)))
                    objects = result.get("objects")
                    object_counts.append(len(objects) if isinstance(objects, list) else 0)
                    centers = _centers_by_label(objects)
                    if baseline_centers is None and centers:
                        baseline_centers = centers
                        baseline_shift = shift_x
                    if baseline_centers:
                        matched_labels = baseline_centers.keys() & centers.keys()
                        identity_coverages.append(len(matched_labels) / len(baseline_centers))
                        expected_delta = shift_x - baseline_shift
                        for label in matched_labels:
                            expected_x = baseline_centers[label][0] + expected_delta
                            center_errors_px.append(abs(centers[label][0] - expected_x))
                    next_frame = max(next_frame + 1.0 / target_fps, time.monotonic())
                    if time.monotonic() >= next_diagnostic:
                        diagnostics = client.get("/api/v1/diagnostics")
                        diagnostics.raise_for_status()
                        sample = diagnostics.json()
                        sample["elapsed_seconds"] = time.monotonic() - started
                        diagnostic_samples.append(sample)
                        next_diagnostic = time.monotonic() + 10.0
                capture_elapsed = time.monotonic() - started
        except BaseException as error:
            capture_error = error
            raise
        finally:
            try:
                deletion = client.delete(
                    f"/api/v1/scenes/{scene_id}",
                    headers=mutation_headers,
                    timeout=300.0,
                )
                deletion.raise_for_status()
            except Exception:
                if capture_error is None:
                    raise

    elapsed = capture_elapsed
    steady_samples = [
        sample
        for sample in diagnostic_samples
        if _number(sample, "elapsed_seconds") >= min(60.0, duration_seconds * 0.2)
    ]
    api_rss = [
        (
            _number(sample, "elapsed_seconds"),
            _number(sample, "api_process_rss_bytes"),
        )
        for sample in steady_samples
    ]
    worker_rss = [
        (
            _number(sample, "elapsed_seconds"),
            _number(sample, "inference_worker_rss_bytes"),
        )
        for sample in steady_samples
        if sample.get("inference_worker_rss_bytes") is not None
    ]
    gpu_used = [
        (
            _number(sample, "elapsed_seconds"),
            _number(gpu, "memory_used_bytes"),
        )
        for sample in steady_samples
        if isinstance((gpu := sample.get("gpu")), dict) and gpu.get("memory_used_bytes") is not None
    ]
    steady_worker_gpu_allocated = [
        sample for sample in worker_gpu_allocated if sample[0] >= min(60.0, duration_seconds * 0.2)
    ]
    steady_worker_gpu_reserved = [
        sample for sample in worker_gpu_reserved if sample[0] >= min(60.0, duration_seconds * 0.2)
    ]
    mib = 1024.0 * 1024.0
    api_slope = _slope_per_minute(api_rss) / mib
    worker_slope = _slope_per_minute(worker_rss) / mib
    gpu_slope = _slope_per_minute(gpu_used) / mib
    worker_gpu_allocated_slope = _slope_per_minute(steady_worker_gpu_allocated) / mib
    worker_gpu_reserved_slope = _slope_per_minute(steady_worker_gpu_reserved) / mib
    p95_latency = float(np.percentile(latencies_ms, 95))
    useful_updates = sequence / elapsed
    maximum_gpu_mib = max((value / mib for _, value in gpu_used), default=0.0)
    identity_coverage = float(np.mean(identity_coverages)) if identity_coverages else 0.0
    p95_center_error = (
        float(np.percentile(center_errors_px, 95)) if center_errors_px else float("inf")
    )
    checks = {
        "useful_updates_at_least_30_per_second": useful_updates >= 30.0,
        "p95_latency_at_most_75_ms": p95_latency <= 75.0,
        "identity_coverage_at_least_0_95": identity_coverage >= 0.95,
        "p95_center_error_at_most_8_px": p95_center_error <= 8.0,
        "gpu_memory_below_7500_mib": maximum_gpu_mib < 7_500.0,
        "api_rss_slope_at_most_2_mib_per_minute": api_slope <= 2.0,
        "worker_rss_slope_at_most_5_mib_per_minute": worker_slope <= 5.0,
        "worker_gpu_reserved_slope_at_most_5_mib_per_minute": bool(steady_worker_gpu_reserved)
        and worker_gpu_reserved_slope <= 5.0,
    }
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "scope": "acknowledgement-paced dynamic learned-provider soak at 640x360",
        "provenance": _provenance(),
        "duration_seconds": elapsed,
        "frames": sequence,
        "useful_updates_per_second": useful_updates,
        "checks": checks,
        "latency_ms": {
            "mean": float(np.mean(latencies_ms)),
            "p50": float(np.percentile(latencies_ms, 50)),
            "p95": p95_latency,
            "maximum": max(latencies_ms),
        },
        "provider_inference_ms": {
            "mean": float(np.mean(provider_latencies_ms)),
            "p50": float(np.percentile(provider_latencies_ms, 50)),
            "p95": float(np.percentile(provider_latencies_ms, 95)),
            "maximum": max(provider_latencies_ms),
        },
        "objects": {
            "minimum": min(object_counts),
            "maximum": max(object_counts),
        },
        "tracking": {
            "baseline_labels": sorted(baseline_centers or {}),
            "mean_identity_coverage": identity_coverage,
            "mean_center_error_px": (
                float(np.mean(center_errors_px)) if center_errors_px else None
            ),
            "p95_center_error_px": p95_center_error,
        },
        "diagnostic_samples": len(diagnostic_samples),
        "steady_state_slope_mib_per_minute": {
            "api_rss": api_slope,
            "inference_worker_rss": worker_slope,
            "worker_gpu_allocated": worker_gpu_allocated_slope,
            "worker_gpu_reserved": worker_gpu_reserved_slope,
            "total_gpu_used_uncontrolled": gpu_slope,
        },
        "steady_state_range_mib": {
            "api_rss": (
                [min(value for _, value in api_rss) / mib, max(value for _, value in api_rss) / mib]
                if api_rss
                else None
            ),
            "inference_worker_rss": (
                [
                    min(value for _, value in worker_rss) / mib,
                    max(value for _, value in worker_rss) / mib,
                ]
                if worker_rss
                else None
            ),
            "gpu_used": (
                [
                    min(value for _, value in gpu_used) / mib,
                    max(value for _, value in gpu_used) / mib,
                ]
                if gpu_used
                else None
            ),
            "worker_gpu_allocated": (
                [
                    min(value for _, value in steady_worker_gpu_allocated) / mib,
                    max(value for _, value in steady_worker_gpu_allocated) / mib,
                ]
                if steady_worker_gpu_allocated
                else None
            ),
            "worker_gpu_reserved": (
                [
                    min(value for _, value in steady_worker_gpu_reserved) / mib,
                    max(value for _, value in steady_worker_gpu_reserved) / mib,
                ]
                if steady_worker_gpu_reserved
                else None
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", required=True)
    parser.add_argument("--duration-seconds", type=int, default=1800)
    parser.add_argument("--target-fps", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = run(
        base_url=arguments.base_url,
        token=arguments.token,
        duration_seconds=arguments.duration_seconds,
        target_fps=arguments.target_fps,
    )
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


if __name__ == "__main__":
    main()
