from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import cast

import cv2
import numpy as np
import pytest

from worldstate_api.providers.base import ProviderObservation
from worldstate_api.providers.models import ModelBundleProvider
from worldstate_api.providers.registry import ModelRegistry


def _textured_frame(*, dx: int = 0, dy: int = 0) -> np.ndarray:
    image = np.zeros((180, 260), dtype=np.uint8)
    cv2.rectangle(image, (70 + dx, 45 + dy), (150 + dx, 135 + dy), 180, thickness=-1)
    cv2.rectangle(image, (82 + dx, 58 + dy), (100 + dx, 77 + dy), 245, thickness=-1)
    cv2.circle(image, (128 + dx, 102 + dy), 13, 35, thickness=-1)
    cv2.line(image, (76 + dx, 128 + dy), (144 + dx, 52 + dy), 75, thickness=3)
    return image


def test_optical_flow_propagates_box_and_relative_position() -> None:
    previous = _textured_frame()
    current = _textured_frame(dx=9, dy=6)
    observation = ProviderObservation(
        label="book",
        confidence=0.9,
        box_xyxy=(70.0, 45.0, 150.0, 135.0),
        position_m=(-0.15, 0.10, 1.2),
        bounds_m=(0.4, 0.25, 0.1),
        embedding=(1.0, 0.0),
    )

    tracked, quality = ModelBundleProvider._track_observations(
        previous,
        current,
        (observation,),
    )

    assert quality > 0.35
    assert tracked[0].box_xyxy == pytest.approx((79.0, 51.0, 159.0, 141.0), abs=2.0)
    assert tracked[0].position_m is not None
    assert tracked[0].position_m[0] > observation.position_m[0]  # type: ignore[index]
    assert tracked[0].position_m[1] < observation.position_m[1]  # type: ignore[index]
    assert tracked[0].bounds_m == observation.bounds_m


def test_half_resolution_tracking_preserves_full_resolution_boxes() -> None:
    previous = cv2.resize(_textured_frame(), (520, 360), interpolation=cv2.INTER_NEAREST)
    current = cv2.resize(
        _textured_frame(dx=9, dy=6),
        (520, 360),
        interpolation=cv2.INTER_NEAREST,
    )
    observation = ProviderObservation(
        label="book",
        confidence=0.9,
        box_xyxy=(140.0, 90.0, 300.0, 270.0),
    )

    tracked, quality = ModelBundleProvider._track_observations(
        previous,
        current,
        (observation,),
    )

    assert quality > 0.35
    assert tracked[0].box_xyxy == pytest.approx(
        (158.0, 102.0, 318.0, 282.0),
        abs=4.0,
    )


def test_large_frame_tracking_uses_bounded_working_resolution() -> None:
    previous = cv2.resize(_textured_frame(), (960, 540), interpolation=cv2.INTER_NEAREST)
    current = previous.copy()
    observation = ProviderObservation(
        label="keys",
        confidence=0.7,
        box_xyxy=(260.0, 135.0, 560.0, 405.0),
    )

    tracked, quality = ModelBundleProvider._track_observations(
        previous,
        current,
        (observation,),
    )

    assert quality > 0.35
    assert tracked[0].box_xyxy == pytest.approx(observation.box_xyxy, abs=5.0)


def test_half_resolution_template_fallback_uses_scaled_box(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous = cv2.resize(_textured_frame(), (520, 360), interpolation=cv2.INTER_NEAREST)
    current = previous.copy()
    observation = ProviderObservation(
        label="notebook",
        confidence=0.5,
        box_xyxy=(140.0, 90.0, 300.0, 270.0),
    )
    monkeypatch.setattr(cv2, "goodFeaturesToTrack", lambda *_args, **_kwargs: None)

    tracked, quality = ModelBundleProvider._track_observations(
        previous,
        current,
        (observation,),
    )

    assert quality > 0.95
    assert tracked[0].box_xyxy == pytest.approx(observation.box_xyxy, abs=2.0)
    assert tracked[0].confidence > 0.49


def test_optical_flow_fails_closed_on_shape_change() -> None:
    observation = ProviderObservation(
        label="cup",
        confidence=0.8,
        box_xyxy=(10.0, 10.0, 30.0, 30.0),
    )

    tracked, quality = ModelBundleProvider._track_observations(
        np.zeros((20, 20), dtype=np.uint8),
        np.zeros((30, 30), dtype=np.uint8),
        (observation,),
    )

    assert tracked == ()
    assert quality == 0.0


def test_discovery_suppresses_same_label_and_cross_label_duplicates() -> None:
    boxes, scores, labels = ModelBundleProvider._suppress_overlaps(
        boxes=[
            [10.0, 10.0, 100.0, 100.0],
            [13.0, 12.0, 98.0, 99.0],
            [11.0, 11.0, 99.0, 98.0],
            [130.0, 20.0, 180.0, 80.0],
        ],
        scores=[0.82, 0.71, 0.77, 0.60],
        labels=["cup", "cup", "bottle", "book"],
    )

    assert scores == [0.82, 0.60]
    assert labels == ["cup", "book"]
    assert boxes == [
        [10.0, 10.0, 100.0, 100.0],
        [130.0, 20.0, 180.0, 80.0],
    ]


def test_discovery_keeps_distinct_instances_of_the_same_label() -> None:
    boxes, scores, labels = ModelBundleProvider._suppress_overlaps(
        boxes=[[5.0, 5.0, 35.0, 35.0], [70.0, 5.0, 100.0, 35.0]],
        scores=[0.8, 0.7],
        labels=["cup", "cup"],
    )

    assert len(boxes) == 2
    assert scores == [0.8, 0.7]
    assert labels == ["cup", "cup"]


def test_specific_label_wins_over_overlapping_unknown_object() -> None:
    boxes, scores, labels = ModelBundleProvider._suppress_overlaps(
        boxes=[[10.0, 10.0, 100.0, 100.0], [11.0, 11.0, 99.0, 99.0]],
        scores=[0.95, 0.72],
        labels=["unknown object", "notebook"],
    )

    assert boxes == [[11.0, 11.0, 99.0, 99.0]]
    assert scores == [0.72]
    assert labels == ["notebook"]


def test_discovery_labels_are_canonicalized_to_one_inventory_category() -> None:
    assert (
        ModelBundleProvider._canonical_discovery_label(
            "headphones earbuds",
            ("headphones", "earbuds"),
        )
        == "earbuds"
    )
    assert (
        ModelBundleProvider._canonical_discovery_label(
            "computer mouse",
            ("keyboard", "computer mouse"),
        )
        == "computer mouse"
    )
    assert (
        ModelBundleProvider._canonical_discovery_label(
            "object",
            ("sticky note", "object"),
        )
        == "unknown object"
    )


def test_discovery_refresh_keeps_independently_tracked_objects() -> None:
    tracked = (
        ProviderObservation("notebook", 0.7, (10.0, 10.0, 80.0, 80.0)),
        ProviderObservation("keys", 0.6, (120.0, 20.0, 150.0, 45.0)),
    )
    discovered = (ProviderObservation("notebook", 0.82, (12.0, 11.0, 81.0, 79.0)),)

    merged = ModelBundleProvider._merge_discovery(tracked, discovered)

    assert [item.label for item in merged] == ["notebook", "keys"]
    assert merged[0].confidence == 0.82


def test_background_discovery_reuses_one_executor_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ModelBundleProvider(cast(ModelRegistry, object()), device="cpu")
    thread_ids: list[int] = []

    def discover(
        _image: np.ndarray,
        _prompts: tuple[str, ...],
    ) -> tuple[ProviderObservation, ...]:
        thread_ids.append(threading.get_ident())
        return ()

    monkeypatch.setattr(provider, "_discover", discover)
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    gray = np.zeros((48, 64), dtype=np.uint8)
    try:
        for sequence in (1, 2):
            provider._start_background_discovery(image, gray, ("cup",), sequence)
            future = provider._discovery_future
            assert future is not None
            future.result(timeout=2.0)
            assert provider._apply_background_discovery(gray)
    finally:
        provider.close()

    assert len(thread_ids) == 2
    assert thread_ids[0] == thread_ids[1]


def test_empty_discovery_waits_for_scheduled_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ModelBundleProvider(
        cast(ModelRegistry, object()),
        device="cpu",
        discovery_interval=12,
        background_discovery=False,
    )
    discoveries = 0

    def discover(
        _image: np.ndarray,
        _prompts: tuple[str, ...],
    ) -> tuple[ProviderObservation, ...]:
        nonlocal discoveries
        discoveries += 1
        return ()

    provider._torch = SimpleNamespace(
        cuda=SimpleNamespace(
            memory_allocated=lambda: 0,
            memory_reserved=lambda: 0,
            is_available=lambda: False,
        )
    )
    monkeypatch.setattr(provider, "_load", lambda: None)
    monkeypatch.setattr(provider, "_discover", discover)
    image = np.zeros((48, 64, 3), dtype=np.uint8)
    try:
        first = provider.observe(image, sequence=0, prompts=("wallet",))
        assert first.discovery_ran is True

        provider.observe(image, sequence=1, prompts=("wallet",))
        for sequence in range(2, 12):
            provider.observe(image, sequence=sequence, prompts=("wallet",))
        assert discoveries == 1

        provider.observe(image, sequence=12, prompts=("wallet",))
        assert discoveries == 2
    finally:
        provider.close()


def test_model_provider_reset_discards_all_session_temporal_state() -> None:
    provider = ModelBundleProvider(cast(ModelRegistry, object()), device="cpu")
    provider._cached = (
        ProviderObservation(
            label="cup",
            confidence=0.9,
            box_xyxy=(10.0, 10.0, 40.0, 50.0),
        ),
    )
    provider._previous_gray = np.ones((12, 12), dtype=np.uint8)
    provider._processed_frames = 42
    provider._last_discovery_sequence = 42
    provider._lost_tracks_since_sequence = 41
    provider._loss_discovery_attempts = 1
    provider._discovery_prompt_batch_index = 2

    try:
        provider.reset()
        assert provider._cached == ()
        assert provider._previous_gray is None
        assert provider._processed_frames == 0
        assert provider._last_discovery_sequence is None
        assert provider._lost_tracks_since_sequence is None
        assert provider._loss_discovery_attempts == 0
        assert provider._discovery_prompt_batch_index == 0
    finally:
        provider.close()


def test_empty_focused_discovery_does_not_erase_validated_tracks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ModelBundleProvider(cast(ModelRegistry, object()), device="cpu")
    provider._cached = (
        ProviderObservation(
            label="notebook",
            confidence=0.7,
            box_xyxy=(10.0, 10.0, 40.0, 40.0),
        ),
    )
    monkeypatch.setattr(provider, "_discover", lambda *_args, **_kwargs: ())
    image = np.zeros((48, 64, 3), dtype=np.uint8)

    try:
        provider._run_discovery(image, ("notebook",), 90)
        assert provider._cached[0].label == "notebook"
        assert provider._lost_tracks_since_sequence is None
        assert provider._loss_discovery_attempts == 0

        provider._run_discovery(image, ("notebook",), 93)
        assert provider._cached[0].label == "notebook"
        assert provider._lost_tracks_since_sequence is None
        assert provider._loss_discovery_attempts == 0
    finally:
        provider.close()


def test_discovery_prompt_batches_rotate_without_omitting_categories() -> None:
    provider = ModelBundleProvider(
        cast(ModelRegistry, object()),
        device="cpu",
        discovery_interval=90,
        maintenance_discovery_interval=300,
    )
    prompts = tuple(f"category-{index}" for index in range(32))
    try:
        assert provider._scheduled_discovery_interval(prompts) == 90
        batches = [provider._next_discovery_prompts(prompts) for _ in range(4)]
        assert provider._scheduled_discovery_interval(prompts) == 300
    finally:
        provider.close()

    assert [len(batch) for batch in batches] == [12, 12, 8, 12]
    assert set((*batches[0], *batches[1], *batches[2])) == set(prompts)
