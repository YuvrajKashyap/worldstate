from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from worldstate_api.artifacts import ArtifactStore
from worldstate_api.persistence import Database, WorldRepository
from worldstate_api.providers.base import ProviderObservation, ProviderResult
from worldstate_api.world_engine import WorldEngine


def _result(*observations: ProviderObservation) -> ProviderResult:
    return ProviderResult(
        observations=tuple(observations),
        inference_ms=4.0,
        discovery_ran=True,
        depth_ran=True,
        embedding_ran=True,
    )


def test_world_engine_builds_temporal_memory_and_scene_graph(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'world.sqlite3').as_posix()}")
    database.create_schema()
    repository = WorldRepository(database)
    artifacts = ArtifactStore(
        root=tmp_path / "artifacts",
        quota_bytes=1_000_000,
        repository=repository,
    )
    engine = WorldEngine(repository=repository, artifact_store=artifacts)
    scene = repository.create_scene(
        name="Desk",
        description=None,
        persistence_enabled=True,
        object_prompts=("cup", "book"),
    )
    capture = repository.create_capture_session(
        scene_id=scene.id,
        mode="live",
        camera=None,
        source_name="test",
    )
    assert capture is not None
    start = datetime(2026, 1, 1, tzinfo=UTC)
    cup = ProviderObservation(
        label="cup",
        confidence=0.95,
        box_xyxy=(0, 0, 20, 20),
        position_m=(0.0, 0.0, 1.0),
        bounds_m=(0.2, 0.3, 0.15),
        embedding=(1.0, 0.0),
        mask_png=b"mask-cup",
    )
    book = ProviderObservation(
        label="book",
        confidence=0.9,
        box_xyxy=(40, 0, 60, 20),
        position_m=(0.5, 0.0, 1.0),
        embedding=(0.0, 1.0),
    )

    initial = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=0,
        captured_at=start,
        width=100,
        height=100,
        quality={"keyframe_score": 1.0},
        provider_result=_result(cup, book),
    )
    assert [event.kind for event in initial.events] == ["added", "added"]
    assert initial.objects[0].mask_artifact_id is not None
    assert initial.objects[0].state.bounds_m == [0.2, 0.3, 0.15]
    assert repository.list_relationships(scene.id)

    moved_cup = ProviderObservation(
        label="cup",
        confidence=0.94,
        box_xyxy=(30, 0, 50, 20),
        position_m=(0.25, 0.0, 1.0),
        embedding=(1.0, 0.0),
    )
    changed = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=1,
        captured_at=start + timedelta(seconds=30),
        width=100,
        height=100,
        quality={"keyframe_score": 1.0},
        provider_result=_result(moved_cup),
    )
    assert "moved" in [event.kind for event in changed.events]
    book_entity = next(
        item.entity for item in initial.objects if item.entity.canonical_label == "book"
    )
    assert repository.get_current_state(book_entity.id).presence == "missing"  # type: ignore[union-attr]

    rediscovered = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=2,
        captured_at=start + timedelta(seconds=31),
        width=100,
        height=100,
        quality={"keyframe_score": 1.0},
        provider_result=_result(book),
    )
    assert "rediscovered" in [event.kind for event in rediscovered.events]
    assert len(repository.list_entity_states(book_entity.id)) == 3
    database.dispose()


def test_world_engine_rejects_unknown_scene(tmp_path: Path) -> None:
    database = Database("sqlite:///:memory:")
    database.create_schema()
    repository = WorldRepository(database)
    engine = WorldEngine(
        repository=repository,
        artifact_store=ArtifactStore(
            root=tmp_path / "artifacts",
            quota_bytes=1_000_000,
            repository=repository,
        ),
    )

    try:
        engine.process(
            scene_id="missing",
            capture_session_id="missing",
            sequence=0,
            captured_at=datetime.now(UTC),
            width=1,
            height=1,
            quality={},
            provider_result=_result(),
        )
    except KeyError as error:
        assert error.args == ("missing",)
    else:
        raise AssertionError("unknown scene was accepted")


def test_world_engine_batches_non_artifact_frame_updates(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'batched.sqlite3').as_posix()}")
    database.create_schema()
    repository = WorldRepository(database)
    engine = WorldEngine(
        repository=repository,
        artifact_store=ArtifactStore(
            root=tmp_path / "artifacts-batched",
            quota_bytes=1_000_000,
            repository=repository,
        ),
    )
    scene = repository.create_scene(
        name="Batched",
        description=None,
        persistence_enabled=False,
        object_prompts=("cup",),
    )
    capture = repository.create_capture_session(
        scene_id=scene.id,
        mode="live",
        camera=None,
        source_name="test",
    )
    assert capture is not None
    observation = ProviderObservation(
        label="cup",
        confidence=0.9,
        box_xyxy=(0, 0, 20, 20),
        position_m=(0.0, 0.0, 1.0),
    )
    started = datetime(2026, 1, 1, tzinfo=UTC)

    for sequence in range(2):
        update = engine.process(
            scene_id=scene.id,
            capture_session_id=capture.id,
            sequence=sequence,
            captured_at=started + timedelta(milliseconds=sequence * 100),
            width=100,
            height=100,
            quality={"keyframe_score": 1.0},
            provider_result=_result(observation),
        )
        assert len(update.objects) == 1

    assert len(repository.list_entity_states(update.objects[0].entity.id)) == 2
    database.dispose()


def test_world_engine_refines_combined_detector_label_without_splitting_identity(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'label-refinement.sqlite3').as_posix()}")
    database.create_schema()
    repository = WorldRepository(database)
    engine = WorldEngine(
        repository=repository,
        artifact_store=ArtifactStore(
            root=tmp_path / "artifacts-label-refinement",
            quota_bytes=1_000_000,
            repository=repository,
        ),
    )
    scene = repository.create_scene(
        name="Labels",
        description=None,
        persistence_enabled=False,
        object_prompts=("headphones", "earbuds"),
    )
    capture = repository.create_capture_session(
        scene_id=scene.id,
        mode="live",
        camera=None,
        source_name="browser-webcam",
    )
    started = datetime(2026, 1, 1, tzinfo=UTC)
    combined = ProviderObservation(
        label="headphones earbuds",
        confidence=0.8,
        box_xyxy=(10, 10, 40, 40),
        embedding=(1.0, 0.0),
    )
    initial = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=0,
        captured_at=started,
        width=100,
        height=100,
        quality={},
        provider_result=_result(combined),
    )
    refined = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=1,
        captured_at=started + timedelta(milliseconds=100),
        width=100,
        height=100,
        quality={},
        provider_result=_result(
            ProviderObservation(
                label="earbuds",
                confidence=0.82,
                box_xyxy=(10, 10, 40, 40),
                embedding=(1.0, 0.0),
            )
        ),
    )

    assert refined.objects[0].entity.id == initial.objects[0].entity.id
    assert refined.objects[0].entity.display_name == "earbuds"
    assert len(repository.list_entities(scene.id)) == 1
    database.dispose()


def test_relative_depth_drift_does_not_create_a_fixed_webcam_move_event(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'depth-drift.sqlite3').as_posix()}")
    database.create_schema()
    repository = WorldRepository(database)
    engine = WorldEngine(
        repository=repository,
        artifact_store=ArtifactStore(
            root=tmp_path / "artifacts-depth-drift",
            quota_bytes=1_000_000,
            repository=repository,
        ),
    )
    scene = repository.create_scene(
        name="Depth drift",
        description=None,
        persistence_enabled=True,
        object_prompts=("laptop",),
    )
    capture = repository.create_capture_session(
        scene_id=scene.id,
        mode="live",
        camera=None,
        source_name="browser-webcam",
    )
    assert capture is not None
    started = datetime(2026, 1, 1, tzinfo=UTC)
    initial = ProviderObservation(
        label="laptop",
        confidence=0.9,
        box_xyxy=(10, 10, 70, 50),
        position_m=(0.0, 0.0, 0.7),
    )
    drifted = ProviderObservation(
        label="laptop",
        confidence=0.89,
        box_xyxy=(11, 10, 71, 50),
        position_m=(0.0, 0.0, 1.2),
    )
    engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=0,
        captured_at=started,
        width=100,
        height=100,
        quality={},
        provider_result=_result(initial),
    )
    update = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=1,
        captured_at=started + timedelta(milliseconds=100),
        width=100,
        height=100,
        quality={},
        provider_result=_result(drifted),
    )

    assert "moved" not in [event.kind for event in update.events]
    database.dispose()


def test_occlusion_removal_and_rediscovery_emit_meaningful_events(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'presence-events.sqlite3').as_posix()}")
    database.create_schema()
    repository = WorldRepository(database)
    engine = WorldEngine(
        repository=repository,
        artifact_store=ArtifactStore(
            root=tmp_path / "artifacts-presence-events",
            quota_bytes=1_000_000,
            repository=repository,
        ),
    )
    scene = repository.create_scene(
        name="Presence lifecycle",
        description=None,
        persistence_enabled=True,
        object_prompts=("cup", "book"),
    )
    capture = repository.create_capture_session(
        scene_id=scene.id,
        mode="live",
        camera=None,
        source_name="browser-webcam",
    )
    assert capture is not None
    started = datetime(2026, 1, 1, tzinfo=UTC)
    cup = ProviderObservation(
        label="cup",
        confidence=0.9,
        box_xyxy=(15, 15, 35, 35),
        embedding=(1.0, 0.0),
    )
    book = ProviderObservation(
        label="book",
        confidence=0.92,
        box_xyxy=(0, 0, 50, 50),
        embedding=(0.0, 1.0),
    )
    initial = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=0,
        captured_at=started,
        width=100,
        height=100,
        quality={},
        provider_result=_result(cup, book),
    )
    cup_id = next(
        item.entity.id for item in initial.objects if item.entity.canonical_label == "cup"
    )

    occluded = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=1,
        captured_at=started + timedelta(milliseconds=100),
        width=100,
        height=100,
        quality={},
        provider_result=_result(book),
    )
    assert "occluded" in [event.kind for event in occluded.events]
    assert repository.get_current_state(cup_id).presence == "occluded"  # type: ignore[union-attr]

    removed = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=2,
        captured_at=started + timedelta(seconds=30),
        width=100,
        height=100,
        quality={},
        provider_result=_result(),
    )
    assert "removed" in [event.kind for event in removed.events]

    rediscovered = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=3,
        captured_at=started + timedelta(seconds=31),
        width=100,
        height=100,
        quality={},
        provider_result=_result(cup),
    )
    assert "rediscovered" in [event.kind for event in rediscovered.events]
    database.dispose()


def test_brief_tracking_gap_is_predicted_without_false_removal_or_rediscovery(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'brief-gap.sqlite3').as_posix()}")
    database.create_schema()
    repository = WorldRepository(database)
    engine = WorldEngine(
        repository=repository,
        artifact_store=ArtifactStore(
            root=tmp_path / "artifacts-brief-gap",
            quota_bytes=1_000_000,
            repository=repository,
        ),
    )
    scene = repository.create_scene(
        name="Brief gap",
        description=None,
        persistence_enabled=True,
        object_prompts=("notebook",),
    )
    capture = repository.create_capture_session(
        scene_id=scene.id,
        mode="live",
        camera=None,
        source_name="browser-webcam",
    )
    started = datetime(2026, 1, 1, tzinfo=UTC)
    notebook = ProviderObservation(
        label="notebook",
        confidence=0.45,
        box_xyxy=(10, 10, 70, 50),
    )
    initial = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=0,
        captured_at=started,
        width=100,
        height=100,
        quality={},
        provider_result=_result(notebook),
    )
    entity_id = initial.objects[0].entity.id

    gap = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=1,
        captured_at=started + timedelta(seconds=2),
        width=100,
        height=100,
        quality={},
        provider_result=_result(),
    )
    assert repository.get_current_state(entity_id).presence == "predicted"  # type: ignore[union-attr]
    assert "removed" not in [event.kind for event in gap.events]

    returned = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=2,
        captured_at=started + timedelta(seconds=3),
        width=100,
        height=100,
        quality={},
        provider_result=_result(notebook),
    )
    assert repository.get_current_state(entity_id).presence == "visible"  # type: ignore[union-attr]
    assert "rediscovered" not in [event.kind for event in returned.events]
    database.dispose()


def test_ephemeral_updates_preserve_identity_without_growing_durable_history(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'ephemeral.sqlite3').as_posix()}")
    database.create_schema()
    repository = WorldRepository(database)
    engine = WorldEngine(
        repository=repository,
        artifact_store=ArtifactStore(
            root=tmp_path / "artifacts-ephemeral",
            quota_bytes=1_000_000,
            repository=repository,
        ),
    )
    scene = repository.create_scene(
        name="Realtime",
        description=None,
        persistence_enabled=False,
        object_prompts=("cup",),
    )
    capture = repository.create_capture_session(
        scene_id=scene.id,
        mode="live",
        camera=None,
        source_name="test",
    )
    assert capture is not None
    started = datetime(2026, 1, 1, tzinfo=UTC)
    initial_observation = ProviderObservation(
        label="cup",
        confidence=0.95,
        box_xyxy=(0, 0, 20, 20),
        position_m=(0.0, 0.0, 1.0),
        embedding=(1.0, 0.0),
    )
    initial = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=0,
        captured_at=started,
        width=100,
        height=100,
        quality={},
        provider_result=_result(initial_observation),
    )
    entity_id = initial.objects[0].entity.id

    moved = ProviderObservation(
        label="cup",
        confidence=0.93,
        box_xyxy=(6, 2, 26, 22),
        position_m=(0.06, 0.02, 1.0),
        bounds_m=(0.21, 0.31, 0.16),
        embedding=(1.0, 0.0),
    )
    live = engine.process_ephemeral(
        scene_id=scene.id,
        captured_at=started + timedelta(milliseconds=33),
        provider_result=_result(moved),
    )
    assert len(live.objects) == 1
    assert live.objects[0].entity.id == entity_id
    assert live.objects[0].state.box_xyxy == [6, 2, 26, 22]
    assert live.objects[0].state.bounds_m == [0.21, 0.31, 0.16]
    assert live.events == ()
    assert len(repository.list_entity_states(entity_id)) == 1

    persisted = engine.process(
        scene_id=scene.id,
        capture_session_id=capture.id,
        sequence=3,
        captured_at=started + timedelta(milliseconds=100),
        width=100,
        height=100,
        quality={},
        provider_result=_result(moved),
    )
    assert persisted.objects[0].entity.id == entity_id
    assert len(repository.list_entity_states(entity_id)) == 2
    database.dispose()
