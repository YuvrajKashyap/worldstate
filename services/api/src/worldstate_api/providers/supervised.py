# pyright: basic, reportMissingTypeStubs=false
"""Supervised shared-memory subprocess boundary for heavyweight inference."""

from __future__ import annotations

import multiprocessing as mp
import os
import queue
import threading
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np

from worldstate_api.providers.base import ProviderResult
from worldstate_api.providers.registry import ModelRegistry


def _worker_main(
    requests: mp.Queue[object],
    responses: mp.Queue[object],
    *,
    mode: Literal["replay", "models"],
    manifest_path: str,
    lock_path: str,
    models_root: str,
) -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    if mode == "replay":
        from worldstate_api.providers.replay import ReplayPerceptionProvider

        provider = ReplayPerceptionProvider()
    else:
        from worldstate_api.providers.models import ModelBundleProvider

        registry = ModelRegistry(
            manifest_path=Path(manifest_path),
            lock_path=Path(lock_path),
            models_root=Path(models_root),
        )
        provider = ModelBundleProvider(registry)
    try:
        while True:
            request = requests.get()
            if request is None:
                return
            if not isinstance(request, tuple) or not request:
                continue
            operation = request[0]
            if operation == "warmup":
                request_id = cast(tuple[str, int], request)[1]
                try:
                    warmup = getattr(provider, "warmup", None)
                    if callable(warmup):
                        warmup()
                    responses.put((request_id, True, None))
                except Exception as error:
                    responses.put(
                        (
                            request_id,
                            False,
                            {
                                "error_type": type(error).__name__,
                                "message": "The isolated inference worker failed to warm up.",
                            },
                        )
                    )
                continue
            if operation == "reset":
                request_id = cast(tuple[str, int], request)[1]
                try:
                    reset = getattr(provider, "reset", None)
                    if callable(reset):
                        reset()
                    responses.put((request_id, True, None))
                except Exception as error:
                    responses.put(
                        (
                            request_id,
                            False,
                            {
                                "error_type": type(error).__name__,
                                "message": "The isolated inference worker failed to reset.",
                            },
                        )
                    )
                continue
            request_values = cast(
                tuple[str, int, str, tuple[int, ...], str, int, tuple[str, ...]],
                request,
            )
            (
                _operation,
                request_id,
                shared_name,
                shape,
                dtype,
                sequence,
                prompts,
            ) = request_values
            shared = SharedMemory(name=shared_name)
            try:
                image = np.ndarray(shape, dtype=np.dtype(dtype), buffer=shared.buf)
                result = provider.observe(
                    image,
                    sequence=sequence,
                    prompts=prompts,
                )
                responses.put((request_id, True, result))
            except Exception as error:
                responses.put(
                    (
                        request_id,
                        False,
                        {
                            "error_type": type(error).__name__,
                            "message": "The isolated inference worker failed.",
                        },
                    )
                )
            finally:
                shared.close()
    finally:
        provider.close()


class SupervisedPerceptionProvider:
    """Proxy inference through a restartable process with shared-memory frames."""

    def __init__(
        self,
        registry: ModelRegistry,
        *,
        mode: Literal["replay", "models"] = "models",
        response_timeout_seconds: float = 180.0,
        warmup_timeout_seconds: float = 420.0,
    ) -> None:
        self.registry = registry
        self.mode = mode
        self.response_timeout_seconds = response_timeout_seconds
        self.warmup_timeout_seconds = warmup_timeout_seconds
        self._context = mp.get_context("spawn")
        self._requests: mp.Queue[object] | None = None
        self._responses: mp.Queue[object] | None = None
        self._process: Any = None
        self._request_id = 0
        self._operation_lock = threading.Lock()

    @property
    def provider_id(self) -> str:
        return f"worldstate.supervised-{self.mode}.v1"

    @property
    def worker_pid(self) -> int | None:
        process = self._process
        pid = getattr(process, "pid", None)
        return int(pid) if isinstance(pid, int) else None

    def _start(self) -> None:
        if self._process is not None and self._process.is_alive():
            return
        if self._process is not None:
            self._stop_process()
        self._requests = self._context.Queue(maxsize=1)
        self._responses = self._context.Queue(maxsize=1)
        self._process = self._context.Process(
            target=_worker_main,
            kwargs={
                "requests": self._requests,
                "responses": self._responses,
                "mode": self.mode,
                "manifest_path": str(self.registry.manifest_path),
                "lock_path": str(self.registry.lock_path),
                "models_root": str(self.registry.models_root),
            },
            name="worldstate-inference",
            daemon=True,
        )
        self._process.start()

    def observe(
        self,
        image_bgr: np.ndarray,
        *,
        sequence: int,
        prompts: tuple[str, ...],
    ) -> ProviderResult:
        with self._operation_lock:
            return self._observe_locked(
                image_bgr,
                sequence=sequence,
                prompts=prompts,
            )

    def _observe_locked(
        self,
        image_bgr: np.ndarray,
        *,
        sequence: int,
        prompts: tuple[str, ...],
    ) -> ProviderResult:
        self._start()
        if self._requests is None or self._responses is None:
            raise RuntimeError("inference worker did not initialize")
        self._request_id += 1
        request_id = self._request_id
        contiguous = np.ascontiguousarray(image_bgr)
        shared = SharedMemory(create=True, size=contiguous.nbytes)
        try:
            shared_view = np.ndarray(contiguous.shape, dtype=contiguous.dtype, buffer=shared.buf)
            shared_view[:] = contiguous
            try:
                self._requests.put(
                    (
                        "observe",
                        request_id,
                        shared.name,
                        contiguous.shape,
                        contiguous.dtype.str,
                        sequence,
                        prompts,
                    ),
                    timeout=0.25,
                )
            except queue.Full as error:
                raise RuntimeError("inference request queue is full") from error
            try:
                response = cast(
                    tuple[int, bool, ProviderResult | dict[str, str]],
                    self._responses.get(timeout=self.response_timeout_seconds),
                )
                response_id, succeeded, payload = response
            except queue.Empty as error:
                self._stop_process()
                raise RuntimeError("inference worker timed out and was stopped") from error
            if response_id != request_id:
                self._stop_process()
                raise RuntimeError("inference worker protocol desynchronized")
            if not succeeded:
                error_payload = cast(dict[str, str], payload)
                raise RuntimeError(error_payload["message"])
            if not isinstance(payload, ProviderResult):
                raise RuntimeError("inference worker returned an invalid result")
            return payload
        finally:
            shared.close()
            shared.unlink()

    def _control(self, operation: Literal["warmup", "reset"]) -> None:
        with self._operation_lock:
            self._start()
            if self._requests is None or self._responses is None:
                raise RuntimeError("inference worker did not initialize")
            self._request_id += 1
            request_id = self._request_id
            try:
                self._requests.put((operation, request_id), timeout=0.25)
            except queue.Full as error:
                raise RuntimeError("inference request queue is full") from error
            try:
                timeout_seconds = (
                    self.warmup_timeout_seconds
                    if operation == "warmup"
                    else self.response_timeout_seconds
                )
                response = cast(
                    tuple[int, bool, dict[str, str] | None],
                    self._responses.get(timeout=timeout_seconds),
                )
            except queue.Empty as error:
                self._stop_process()
                raise RuntimeError("inference worker timed out and was stopped") from error
            response_id, succeeded, payload = response
            if response_id != request_id:
                self._stop_process()
                raise RuntimeError("inference worker protocol desynchronized")
            if not succeeded:
                error_payload = cast(dict[str, str], payload)
                raise RuntimeError(error_payload["message"])

    def warmup(self) -> None:
        """Start the worker and load models once for the application lifetime."""

        self._control("warmup")

    def reset(self) -> None:
        """Clear per-capture temporal state without unloading model weights."""

        self._control("reset")

    def _stop_process(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.is_alive():
            process.terminate()
        process.join(timeout=5)
        if self._requests is not None:
            self._requests.close()
        if self._responses is not None:
            self._responses.close()
        self._requests = None
        self._responses = None

    def close(self) -> None:
        if self._process is not None and self._process.is_alive() and self._requests is not None:
            try:
                self._requests.put(None, timeout=0.25)
                self._process.join(timeout=10)
            except queue.Full:
                pass
        self._stop_process()
