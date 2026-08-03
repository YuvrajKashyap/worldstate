from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from worldstate_api.artifacts import ArtifactError, ArtifactStore, StorageQuotaExceeded
from worldstate_api.jobs import JobManager, JobQueueFull
from worldstate_api.persistence import Database, WorldRepository


@pytest.fixture
def repository(tmp_path: Path) -> WorldRepository:
    database = Database(f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}")
    database.create_schema()
    try:
        yield WorldRepository(database)
    finally:
        database.dispose()


def test_nested_repository_calls_share_one_atomic_transaction(
    repository: WorldRepository,
) -> None:
    with (
        pytest.raises(
            RuntimeError,
            match="rollback",
        ),
        repository.database.transaction(),
    ):
        scene = repository.create_scene(
            name="Rolled back",
            description=None,
            persistence_enabled=False,
            object_prompts=("cup",),
        )
        assert repository.get_scene(scene.id) is not None
        raise RuntimeError("rollback")
    assert repository.list_scenes() == []

    with repository.database.transaction():
        repository.create_scene(
            name="Committed",
            description=None,
            persistence_enabled=False,
            object_prompts=("book",),
        )
    assert [scene.name for scene, _count in repository.list_scenes()] == ["Committed"]


def test_scene_session_entity_history_and_cascade(repository: WorldRepository) -> None:
    scene = repository.create_scene(
        name="Desk",
        description=None,
        persistence_enabled=True,
        object_prompts=("cup",),
    )
    capture = repository.create_capture_session(
        scene_id=scene.id,
        mode="live",
        camera={"width": 640, "height": 360},
        source_name="webcam",
    )
    assert capture is not None
    assert repository.activate_capture_session(capture.id).status == "active"  # type: ignore[union-attr]

    first_at = datetime(2026, 1, 1, tzinfo=UTC)
    entity = repository.create_entity(
        scene_id=scene.id,
        label="cup",
        layer="persistent",
        observed_at=first_at,
    )
    first = repository.append_entity_state(
        entity_id=entity.id,
        valid_from=first_at,
        presence="visible",
        confidence=0.9,
        uncertainty=0.1,
        position_m=(0, 0, 1),
        quaternion_xyzw=None,
        bounds_m=(0.1, 0.1, 0.2),
        box_xyxy=(0, 0, 10, 10),
        evidence_ids=(),
    )
    second_at = first_at + timedelta(seconds=1)
    second = repository.append_entity_state(
        entity_id=entity.id,
        valid_from=second_at,
        presence="missing",
        confidence=0.5,
        uncertainty=0.5,
        position_m=(0, 0, 1),
        quaternion_xyzw=None,
        bounds_m=None,
        box_xyxy=None,
        evidence_ids=(),
    )

    states = repository.list_entity_states(entity.id)
    assert states[0].id == first.id
    assert states[0].valid_to is not None
    assert states[1].id == second.id
    assert repository.get_current_state(entity.id).presence == "missing"  # type: ignore[union-attr]
    assert repository.get_current_state(entity.id, at=first_at).presence == "visible"  # type: ignore[union-attr]

    repository.create_event(
        scene_id=scene.id,
        entity_id=entity.id,
        kind="moved",
        occurred_at=second_at,
        confidence=0.8,
        evidence_ids=(),
        payload={"distance_m": 0.2},
    )
    assert repository.list_events(scene.id)[0].kind == "moved"
    assert repository.finish_capture_session(capture.id).status == "completed"  # type: ignore[union-attr]
    assert repository.delete_scene(scene.id)
    assert repository.get_scene(scene.id) is None
    assert repository.get_entity(entity.id) is None


def test_relationship_replacement_closes_previous_interval(
    repository: WorldRepository,
) -> None:
    scene = repository.create_scene(
        name="Desk",
        description=None,
        persistence_enabled=False,
        object_prompts=("cup", "book"),
    )
    now = datetime.now(UTC)
    cup = repository.create_entity(
        scene_id=scene.id, label="cup", layer="persistent", observed_at=now
    )
    book = repository.create_entity(
        scene_id=scene.id, label="book", layer="persistent", observed_at=now
    )
    first = repository.replace_relationships(
        scene_id=scene.id,
        observed_at=now,
        relationships=((cup.id, book.id, "left_of", 0.8),),
    )
    later = now + timedelta(seconds=1)
    repository.replace_relationships(
        scene_id=scene.id,
        observed_at=later,
        relationships=((cup.id, book.id, "near", 0.7),),
    )

    assert repository.list_relationships(scene.id)[0].kind == "near"
    assert repository.list_relationships(scene.id, at=now)[0].id == first[0].id


def test_relationship_replacement_keeps_unchanged_interval_open(
    repository: WorldRepository,
) -> None:
    scene = repository.create_scene(
        name="Desk",
        description=None,
        persistence_enabled=False,
        object_prompts=("cup", "book"),
    )
    now = datetime.now(UTC)
    cup = repository.create_entity(
        scene_id=scene.id, label="cup", layer="persistent", observed_at=now
    )
    book = repository.create_entity(
        scene_id=scene.id, label="book", layer="persistent", observed_at=now
    )
    first = repository.replace_relationships(
        scene_id=scene.id,
        observed_at=now,
        relationships=((cup.id, book.id, "left_of", 0.8),),
    )
    unchanged = repository.replace_relationships(
        scene_id=scene.id,
        observed_at=now + timedelta(seconds=1),
        relationships=((cup.id, book.id, "left_of", 0.81),),
    )

    assert unchanged[0].id == first[0].id
    assert (
        repository.list_relationships(scene.id, at=now + timedelta(seconds=1))[0].id == first[0].id
    )


def test_list_current_states_batches_scene_lookup(repository: WorldRepository) -> None:
    scene = repository.create_scene(
        name="Desk",
        description=None,
        persistence_enabled=False,
        object_prompts=("cup",),
    )
    now = datetime.now(UTC)
    entity = repository.create_entity(
        scene_id=scene.id, label="cup", layer="persistent", observed_at=now
    )
    state = repository.append_entity_state(
        entity_id=entity.id,
        valid_from=now,
        presence="visible",
        confidence=0.9,
        uncertainty=0.1,
        position_m=(0.0, 0.0, 1.0),
        quaternion_xyzw=None,
        bounds_m=(0.2, 0.2, 0.2),
        box_xyxy=(10.0, 10.0, 30.0, 30.0),
        evidence_ids=(),
    )

    assert repository.list_current_states(scene.id)[entity.id].id == state.id


def test_artifact_store_is_content_addressed_bounded_and_collectable(
    repository: WorldRepository,
    tmp_path: Path,
) -> None:
    store = ArtifactStore(root=tmp_path / "artifacts", quota_bytes=100, repository=repository)
    first = store.put_bytes(b"payload", media_type="application/json", kind="test")
    duplicate = store.put_bytes(b"payload", media_type="application/json", kind="test")

    assert duplicate.id == first.id
    assert store.read_bytes(first.id) == b"payload"
    assert store.resolve_trusted_path(first.id).is_file()
    with pytest.raises(ArtifactError, match="read limit"):
        store.read_bytes(first.id, maximum_bytes=1)
    with pytest.raises(ArtifactError, match="size limit"):
        store.put_chunks(
            (b"abc", b"def"),
            media_type="application/octet-stream",
            kind="test",
            maximum_bytes=5,
        )
    with pytest.raises(StorageQuotaExceeded):
        store.put_bytes(b"x" * 101, media_type="application/octet-stream", kind="test")

    removed, reclaimed = store.collect_orphans()
    assert (removed, reclaimed) == (1, len(b"payload"))
    with pytest.raises(FileNotFoundError):
        store.read_bytes(first.id)


def test_database_recovers_interrupted_jobs(repository: WorldRepository) -> None:
    job = repository.create_job(
        kind="evaluation",
        scene_id=None,
        session_id=None,
        parameters={},
    )
    repository.update_job(job.id, status="running", stage="work")

    recovered = repository.database.recover_interrupted_jobs()
    current = repository.get_job(job.id)

    assert recovered == 1
    assert current is not None
    assert current.status == "failed"
    assert current.error_code == "runtime_restarted"


def test_job_manager_success_failure_cancellation_and_queue_bound(
    repository: WorldRepository,
) -> None:
    manager = JobManager(repository=repository, maximum_pending=1, workers=1)
    gate = threading.Event()

    def blocking(context: object) -> dict[str, object]:
        gate.wait(timeout=2)
        return {"ok": True}

    def failing(context: object) -> dict[str, object]:
        raise RuntimeError("private failure detail")

    manager.register("blocking", blocking)  # type: ignore[arg-type]
    manager.register("failing", failing)  # type: ignore[arg-type]
    try:
        first = manager.submit(kind="blocking", scene_id=None, session_id=None, parameters={})
        with pytest.raises(JobQueueFull):
            manager.submit(kind="blocking", scene_id=None, session_id=None, parameters={})
        cancelled = manager.cancel(first.id)
        assert cancelled is not None
        assert cancelled.cancellation_requested
        gate.set()

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            current = repository.get_job(first.id)
            if current is not None and current.status == "cancelled":
                break
            time.sleep(0.01)
        assert repository.get_job(first.id).status == "cancelled"  # type: ignore[union-attr]

        failed = manager.submit(kind="failing", scene_id=None, session_id=None, parameters={})
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            current = repository.get_job(failed.id)
            if current is not None and current.status == "failed":
                break
            time.sleep(0.01)
        current = repository.get_job(failed.id)
        assert current is not None
        assert current.error_code == "RuntimeError"
        assert "private failure detail" not in str(current.error_message)
        with pytest.raises(ValueError, match="registered"):
            manager.register("failing", failing)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="no handler"):
            manager.submit(kind="unknown", scene_id=None, session_id=None, parameters={})
    finally:
        manager.close()
