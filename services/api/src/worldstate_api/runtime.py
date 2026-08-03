"""Bounded provider lifecycle and single-GPU scheduling."""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Literal

from worldstate_api.providers.base import LivePerceptionProvider
from worldstate_api.providers.classical import ClassicalMotionProvider
from worldstate_api.providers.registry import ModelRegistry
from worldstate_api.providers.replay import ReplayPerceptionProvider


class RuntimeBusyError(RuntimeError):
    pass


class GpuScheduler:
    """Coordinate live ownership and exclusive heavyweight jobs."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._live_sessions = 0
        self._exclusive_active = False
        self._closed = False

    def start_live(self) -> None:
        with self._condition:
            if self._closed:
                raise RuntimeBusyError("runtime is shutting down")
            if self._exclusive_active:
                raise RuntimeBusyError("an exclusive GPU job is active")
            if self._live_sessions >= 1:
                raise RuntimeBusyError("a live GPU session is already active")
            self._live_sessions += 1

    def stop_live(self) -> None:
        with self._condition:
            self._live_sessions = max(0, self._live_sessions - 1)
            self._condition.notify_all()

    @property
    def live_sessions(self) -> int:
        with self._condition:
            return self._live_sessions

    @contextmanager
    def exclusive(self, cancellation: threading.Event) -> Generator[None]:
        with self._condition:
            while self._live_sessions > 0 or self._exclusive_active:
                if self._closed or cancellation.is_set():
                    raise RuntimeBusyError("exclusive job was cancelled before acquiring the GPU")
                self._condition.wait(timeout=0.25)
            self._exclusive_active = True
        try:
            yield None
        finally:
            with self._condition:
                self._exclusive_active = False
                self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()


class ProviderFactory:
    def __init__(self, *, mode: Literal["replay", "classical", "models"], registry: ModelRegistry):
        self.mode = mode
        self.registry = registry
        self._lock = threading.Lock()
        self._shared_models_provider: LivePerceptionProvider | None = None

    def create(
        self,
        mode: Literal["replay", "classical", "models"] | None = None,
    ) -> LivePerceptionProvider:
        selected = mode or self.mode
        if selected == "replay":
            return ReplayPerceptionProvider()
        if selected == "classical":
            return ClassicalMotionProvider()
        from worldstate_api.providers.supervised import SupervisedPerceptionProvider

        with self._lock:
            if self._shared_models_provider is None:
                self._shared_models_provider = SupervisedPerceptionProvider(self.registry)
            provider = self._shared_models_provider
            reset = getattr(provider, "reset", None)
            if callable(reset):
                reset()
            return provider

    def warmup(self) -> None:
        """Load the shared learned provider before accepting browser traffic."""

        if self.mode != "models":
            return
        from worldstate_api.providers.supervised import SupervisedPerceptionProvider

        with self._lock:
            if self._shared_models_provider is None:
                self._shared_models_provider = SupervisedPerceptionProvider(self.registry)
            provider = self._shared_models_provider
        warmup = getattr(provider, "warmup", None)
        if callable(warmup):
            warmup()

    def release(self, provider: LivePerceptionProvider) -> None:
        if self.mode == "models" and provider is self._shared_models_provider:
            reset = getattr(provider, "reset", None)
            if callable(reset):
                reset()
            return
        provider.close()

    def suspend(self) -> None:
        """Release learned-model VRAM before an exclusive reconstruction job."""

        if self.mode != "models":
            return
        self.close()

    @property
    def worker_pid(self) -> int | None:
        with self._lock:
            provider = self._shared_models_provider
        pid = getattr(provider, "worker_pid", None)
        return int(pid) if isinstance(pid, int) else None

    def close(self) -> None:
        with self._lock:
            provider = self._shared_models_provider
            self._shared_models_provider = None
        if provider is not None:
            provider.close()
