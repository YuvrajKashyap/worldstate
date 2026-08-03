from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import cv2
import numpy as np
import pytest

from worldstate_api.geometry import (
    MediaValidationError,
    ScanPipeline,
    VideoMetadata,
    _binary_export,
    inspect_video,
    select_keyframes,
)
from worldstate_api.jobs import JobCancelled, JobContext
from worldstate_api.persistence import WorldRepository


def _write_test_video(path: Path) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (160, 120),
    )
    assert writer.isOpened()
    generator = np.random.default_rng(7)
    try:
        for index in range(20):
            image = generator.integers(0, 256, (120, 160, 3), dtype=np.uint8)
            cv2.putText(
                image,
                str(index),
                (20 + index, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 255, 255),
                2,
            )
            writer.write(image)
    finally:
        writer.release()


def test_video_inspection_and_keyframe_selection(tmp_path: Path) -> None:
    video = tmp_path / "views.avi"
    _write_test_video(video)

    metadata = inspect_video(video, maximum_duration_seconds=10)
    keyframes = select_keyframes(video, metadata, maximum_keyframes=6)

    assert metadata == VideoMetadata(160, 120, 20, 10.0, 2.0)
    assert 2 <= len(keyframes) <= 6
    assert all(frame.image_bgr.shape == (120, 160, 3) for frame in keyframes)


def test_video_validation_rejects_undecodable_and_overlong_media(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.mp4"
    invalid.write_bytes(b"not-video")
    with pytest.raises(MediaValidationError, match="cannot be decoded"):
        inspect_video(invalid, maximum_duration_seconds=10)

    video = tmp_path / "views.avi"
    _write_test_video(video)
    with pytest.raises(MediaValidationError, match="duration"):
        inspect_video(video, maximum_duration_seconds=1)


def test_binary_geometry_exports_fail_closed_on_non_binary_output() -> None:
    assert _binary_export(memoryview(b"mesh"), file_type="glb") == b"mesh"
    with pytest.raises(RuntimeError, match="did not produce binary data"):
        _binary_export({"unexpected": "scene"}, file_type="glb")


def test_reconstruction_process_is_terminated_when_job_is_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        exitcode = None

        def __init__(self) -> None:
            self.alive = True
            self.started = False
            self.terminated = False

        def start(self) -> None:
            self.started = True

        def is_alive(self) -> bool:
            return self.alive

        def join(self, timeout: float | None = None) -> None:
            _ = timeout

        def terminate(self) -> None:
            self.terminated = True
            self.alive = False

        def kill(self) -> None:
            self.alive = False

    process = FakeProcess()
    context_factory = SimpleNamespace(Process=lambda **_kwargs: process)
    monkeypatch.setattr(
        "worldstate_api.geometry.mp.get_context",
        lambda _method: context_factory,
    )
    pipeline = ScanPipeline.__new__(ScanPipeline)
    pipeline.model_registry = SimpleNamespace(trusted_path=lambda _model_id: tmp_path / "model")
    cancellation = threading.Event()
    cancellation.set()
    context = JobContext(
        job_id="job",
        scene_id=None,
        session_id=None,
        parameters={},
        cancellation=cancellation,
        _repository=cast(WorldRepository, object()),
    )

    with pytest.raises(JobCancelled):
        pipeline._reconstruct([tmp_path / "frame.jpg"], context)

    assert process.started
    assert process.terminated
