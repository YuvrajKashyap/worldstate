"""Persistent cancellable jobs with bounded local execution."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime

from worldstate_api.persistence import JobModel, WorldRepository


class JobCancelled(RuntimeError):
    pass


class JobQueueFull(RuntimeError):
    pass


JobHandler = Callable[["JobContext"], dict[str, object]]


@dataclass(slots=True)
class JobContext:
    job_id: str
    scene_id: str | None
    session_id: str | None
    parameters: dict[str, object]
    cancellation: threading.Event
    _repository: WorldRepository

    def check_cancelled(self) -> None:
        if self.cancellation.is_set():
            raise JobCancelled("job cancellation was requested")

    def update(self, *, progress: float, stage: str) -> None:
        self.check_cancelled()
        self._repository.update_job(
            self.job_id,
            progress=max(0.0, min(1.0, progress)),
            stage=stage[:120],
        )


class JobManager:
    """Dispatch jobs without allowing an unbounded in-memory queue."""

    def __init__(
        self,
        *,
        repository: WorldRepository,
        maximum_pending: int,
        workers: int = 2,
    ) -> None:
        self.repository = repository
        self.maximum_pending = maximum_pending
        self._executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="worldstate-job",
        )
        self._handlers: dict[str, JobHandler] = {}
        self._cancellations: dict[str, threading.Event] = {}
        self._futures: dict[str, Future[dict[str, object]]] = {}
        self._lock = threading.Lock()

    def register(self, kind: str, handler: JobHandler) -> None:
        if kind in self._handlers:
            raise ValueError(f"a handler is already registered for {kind}")
        self._handlers[kind] = handler

    def submit(
        self,
        *,
        kind: str,
        scene_id: str | None,
        session_id: str | None,
        parameters: dict[str, object],
    ) -> JobModel:
        if kind not in self._handlers:
            raise ValueError(f"no handler is registered for {kind}")
        if self.repository.count_pending_jobs() >= self.maximum_pending:
            raise JobQueueFull("the bounded job queue is full")
        job = self.repository.create_job(
            kind=kind,
            scene_id=scene_id,
            session_id=session_id,
            parameters=parameters,
        )
        cancellation = threading.Event()
        with self._lock:
            self._cancellations[job.id] = cancellation
            self._futures[job.id] = self._executor.submit(
                self._run,
                job,
                cancellation,
            )
        return job

    def _run(
        self,
        job: JobModel,
        cancellation: threading.Event,
    ) -> dict[str, object]:
        self.repository.update_job(
            job.id,
            status="running",
            stage="starting",
            started_at=datetime.now(UTC),
        )
        context = JobContext(
            job_id=job.id,
            scene_id=job.scene_id,
            session_id=job.session_id,
            parameters=job.parameters,
            cancellation=cancellation,
            _repository=self.repository,
        )
        try:
            result = self._handlers[job.kind](context)
            context.check_cancelled()
            self.repository.update_job(
                job.id,
                status="succeeded",
                progress=1.0,
                stage="completed",
                result=result,
                finished_at=datetime.now(UTC),
            )
            return result
        except JobCancelled:
            self.repository.update_job(
                job.id,
                status="cancelled",
                stage="cancelled",
                error_code=None,
                error_message=None,
                finished_at=datetime.now(UTC),
            )
            return {"cancelled": True}
        except Exception as error:
            self.repository.update_job(
                job.id,
                status="failed",
                stage="failed",
                error_code=type(error).__name__,
                error_message="The job failed. Inspect local structured logs for details.",
                finished_at=datetime.now(UTC),
            )
            raise
        finally:
            with self._lock:
                self._cancellations.pop(job.id, None)
                self._futures.pop(job.id, None)

    def cancel(self, job_id: str) -> JobModel | None:
        job = self.repository.get_job(job_id)
        if job is None:
            return None
        if job.status not in {"queued", "running", "cancelling"}:
            return job
        self.repository.update_job(
            job_id,
            status="cancelling",
            cancellation_requested=True,
            stage="cancelling",
        )
        with self._lock:
            cancellation = self._cancellations.get(job_id)
            if cancellation is not None:
                cancellation.set()
        return self.repository.get_job(job_id)

    def close(self) -> None:
        with self._lock:
            for cancellation in self._cancellations.values():
                cancellation.set()
        self._executor.shutdown(wait=True, cancel_futures=True)
