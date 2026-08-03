from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import numpy as np
import pytest

from worldstate_api.contracts import ModelState
from worldstate_api.providers.classical import ClassicalMotionProvider
from worldstate_api.providers.registry import ModelManifestError, ModelRegistry
from worldstate_api.providers.replay import ReplayPerceptionProvider
from worldstate_api.providers.supervised import SupervisedPerceptionProvider
from worldstate_api.runtime import GpuScheduler, ProviderFactory, RuntimeBusyError
from worldstate_api.security import SessionRegistry, SlidingWindowRateLimiter


def _manifest(path: Path, *, revision: str = "abc123", relative_path: str = "model") -> None:
    path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "models:",
                "  - id: demo",
                "    display_name: Demo",
                "    capability: detection",
                "    license: Apache-2.0",
                "    source: https://example.invalid/demo",
                f"    revision: {revision}",
                f"    relative_path: {relative_path}",
                "    required: true",
                "    gated: false",
            ]
        ),
        encoding="utf-8",
    )


def test_model_registry_requires_pin_containment_and_matching_lock(tmp_path: Path) -> None:
    manifest = tmp_path / "models.yaml"
    lock = tmp_path / "models.lock.json"
    models = tmp_path / "models"
    _manifest(manifest)
    registry = ModelRegistry(manifest_path=manifest, lock_path=lock, models_root=models)

    spec = registry.get_spec("demo")
    assert registry.verify(spec) is ModelState.NOT_INSTALLED
    model_path = models / "model"
    model_path.mkdir(parents=True)
    weight = model_path / "weights.safetensors"
    weight.write_bytes(b"verified")
    assert registry.verify(spec) is ModelState.INVALID

    lock.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "models": {
                    "demo": {
                        "revision": "abc123",
                        "files": {"weights.safetensors": hashlib.sha256(b"verified").hexdigest()},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    assert registry.quick_state(spec) is ModelState.AVAILABLE
    assert registry.verify(spec) is ModelState.AVAILABLE
    assert registry.trusted_path("demo") == model_path.resolve()
    weight.write_bytes(b"tampered")
    assert registry.quick_state(spec) is ModelState.AVAILABLE
    assert registry.verify(spec) is ModelState.INVALID
    with pytest.raises(ModelManifestError, match="not installed and verified"):
        registry.trusted_path("demo")
    with pytest.raises(KeyError):
        registry.get_spec("missing")


@pytest.mark.parametrize(
    "revision,relative_path,message",
    [
        ("main", "model", "immutable revision"),
        ("abc123", "../escape", "escapes"),
    ],
)
def test_model_registry_rejects_unsafe_manifests(
    tmp_path: Path,
    revision: str,
    relative_path: str,
    message: str,
) -> None:
    manifest = tmp_path / "models.yaml"
    _manifest(manifest, revision=revision, relative_path=relative_path)
    with pytest.raises(ModelManifestError, match=message):
        ModelRegistry(
            manifest_path=manifest,
            lock_path=tmp_path / "lock.json",
            models_root=tmp_path / "models",
        )


def test_session_registry_one_time_exchange_authenticate_and_revoke() -> None:
    registry = SessionRegistry(bootstrap_token="x" * 40, ttl_seconds=300)
    assert registry.exchange("wrong") is None
    principal = registry.exchange("x" * 40)
    assert principal is not None
    assert registry.exchange("x" * 40) is None
    assert registry.authenticate(principal.token) == principal
    registry.revoke(principal.token)
    assert registry.authenticate(principal.token) is None


def test_rate_limiter_is_bounded_per_key() -> None:
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=60)
    assert limiter.allow("client")
    assert limiter.allow("client")
    assert not limiter.allow("client")
    assert limiter.allow("other")


def test_gpu_scheduler_enforces_live_and_exclusive_ownership() -> None:
    scheduler = GpuScheduler()
    cancellation = threading.Event()
    scheduler.start_live()
    assert scheduler.live_sessions == 1
    with pytest.raises(RuntimeBusyError, match="already active"):
        scheduler.start_live()
    cancellation.set()
    with pytest.raises(RuntimeBusyError, match="cancelled"), scheduler.exclusive(cancellation):
        pass
    scheduler.stop_live()

    cancellation.clear()
    with scheduler.exclusive(cancellation), pytest.raises(RuntimeBusyError, match="exclusive"):
        scheduler.start_live()
    scheduler.close()
    with pytest.raises(RuntimeBusyError, match="shutting down"):
        scheduler.start_live()


def test_replay_and_classical_providers_are_cpu_usable() -> None:
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    replay = ReplayPerceptionProvider()
    result = replay.observe(image, sequence=12, prompts=("cup", "book"))
    assert replay.provider_id == "worldstate.replay.v1"
    assert [item.label for item in result.observations] == ["cup", "book"]
    assert result.discovery_ran and result.depth_ran and result.embedding_ran
    replay.close()

    classical = ClassicalMotionProvider(minimum_area_ratio=0.0001)
    _ = classical.observe(image, sequence=0, prompts=())
    changed = image.copy()
    changed[20:100, 20:120] = 255
    motion = classical.observe(changed, sequence=1, prompts=("object",))
    assert classical.provider_id == "worldstate.opencv-motion.v1"
    assert motion.discovery_ran
    assert motion.depth_ran is False
    classical.close()


def test_provider_factory_honors_capture_specific_replay_mode(tmp_path: Path) -> None:
    registry = ModelRegistry(
        manifest_path=tmp_path / "missing.yaml",
        lock_path=tmp_path / "missing.lock",
        models_root=tmp_path / "models",
    )
    factory = ProviderFactory(mode="models", registry=registry)
    provider = factory.create("replay")
    try:
        assert isinstance(provider, ReplayPerceptionProvider)
        assert factory.worker_pid is None
    finally:
        factory.release(provider)


def test_supervised_provider_uses_shared_memory_and_recovers_after_exit(
    tmp_path: Path,
) -> None:
    registry = ModelRegistry(
        manifest_path=tmp_path / "missing.yaml",
        lock_path=tmp_path / "missing.lock",
        models_root=tmp_path / "models",
    )
    provider = SupervisedPerceptionProvider(
        registry,
        mode="replay",
        response_timeout_seconds=10,
        warmup_timeout_seconds=20,
    )
    assert provider.warmup_timeout_seconds == 20
    image = np.zeros((32, 32, 3), dtype=np.uint8)
    try:
        first = provider.observe(image, sequence=0, prompts=("cup",))
        assert first.observations[0].label == "cup"
        process = provider._process
        assert process is not None
        process.terminate()
        process.join(timeout=5)
        second = provider.observe(image, sequence=1, prompts=("book",))
        assert second.observations[0].label == "book"
    finally:
        provider.close()


def test_provider_factory_resets_shared_models_at_session_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ModelRegistry(
        manifest_path=tmp_path / "missing.yaml",
        lock_path=tmp_path / "missing.lock",
        models_root=tmp_path / "models",
    )

    class FakeModelsProvider:
        def __init__(self, _registry: ModelRegistry) -> None:
            self.reset_calls = 0
            self.close_calls = 0

        def reset(self) -> None:
            self.reset_calls += 1

        def close(self) -> None:
            self.close_calls += 1

    fake = FakeModelsProvider(registry)
    monkeypatch.setattr(
        "worldstate_api.providers.supervised.SupervisedPerceptionProvider",
        lambda _registry: fake,
    )
    factory = ProviderFactory(mode="models", registry=registry)

    first = factory.create("models")
    assert first is fake
    assert fake.reset_calls == 1
    factory.release(first)
    assert fake.reset_calls == 2

    second = factory.create("models")
    assert second is fake
    assert fake.reset_calls == 3
    factory.release(second)
    assert fake.reset_calls == 4

    factory.close()
    assert fake.close_calls == 1
