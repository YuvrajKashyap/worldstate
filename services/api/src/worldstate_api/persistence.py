"""SQLite persistence and transactional repositories."""

from __future__ import annotations

from collections.abc import Generator, Sequence
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from threading import RLock, local
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
    select,
    update,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from worldstate_core.ids import uuid7


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class SceneModel(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    persistence_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    object_prompts: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    coordinate_frame: Mapped[str] = mapped_column(
        String(64), nullable=False, default="worldstate_scene_v1"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CaptureSessionModel(Base):
    __tablename__ = "capture_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scene_id: Mapped[str] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    camera: Mapped[dict[str, object] | None] = mapped_column(JSON)
    source_name: Mapped[str | None] = mapped_column(String(160))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ArtifactModel(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    ref_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_delete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ArtifactReferenceModel(Base):
    """Reference-counted ownership edge used for verified lifecycle deletion."""

    __tablename__ = "artifact_references"
    __table_args__ = (
        UniqueConstraint(
            "artifact_id",
            "scene_id",
            "session_id",
            "job_id",
            "purpose",
            name="uq_artifact_owner_purpose",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_id: Mapped[str | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("capture_sessions.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FrameModel(Base):
    __tablename__ = "frames"
    __table_args__ = (Index("ix_frames_session_sequence", "session_id", "sequence", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("capture_sessions.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifacts.id", ondelete="SET NULL"))
    pose: Mapped[list[float] | None] = mapped_column(JSON)
    quality: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelRunModel(Base):
    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    model_revision: Mapped[str] = mapped_column(String(160), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    device: Mapped[str] = mapped_column(String(32), nullable=False)
    precision: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class ObservationModel(Base):
    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    frame_id: Mapped[str] = mapped_column(
        ForeignKey("frames.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_runs.id", ondelete="SET NULL")
    )
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    box_xyxy: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    position_m: Mapped[list[float] | None] = mapped_column(JSON)
    covariance: Mapped[list[float] | None] = mapped_column(JSON)
    mask_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    embedding_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EntityModel(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scene_id: Mapped[str] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    canonical_label: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    layer: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class EntityStateModel(Base):
    __tablename__ = "entity_states"
    __table_args__ = (Index("ix_entity_states_entity_time", "entity_id", "valid_from"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    presence: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    uncertainty: Mapped[float] = mapped_column(Float, nullable=False)
    position_m: Mapped[list[float] | None] = mapped_column(JSON)
    quaternion_xyzw: Mapped[list[float] | None] = mapped_column(JSON)
    bounds_m: Mapped[list[float] | None] = mapped_column(JSON)
    box_xyxy: Mapped[list[float] | None] = mapped_column(JSON)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class EvidenceModel(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scene_id: Mapped[str] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    frame_id: Mapped[str | None] = mapped_column(ForeignKey("frames.id", ondelete="SET NULL"))
    artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifacts.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorldEventModel(Base):
    __tablename__ = "world_events"
    __table_args__ = (Index("ix_world_events_scene_time", "scene_id", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scene_id: Mapped[str] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class RelationshipModel(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        Index(
            "ix_relationship_identity_time",
            "scene_id",
            "subject_entity_id",
            "object_entity_id",
            "kind",
            "valid_from",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scene_id: Mapped[str] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )
    subject_entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    object_entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobModel(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_created", "status", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    scene_id: Mapped[str | None] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"))
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("capture_sessions.id", ondelete="CASCADE")
    )
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stage: Mapped[str] = mapped_column(String(120), nullable=False, default="queued")
    result: Mapped[dict[str, object] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExportModel(Base):
    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scene_id: Mapped[str] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    formats: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    artifact_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Database:
    """Own the SQLAlchemy engine and short-lived transactional sessions."""

    def __init__(self, url: str) -> None:
        engine_kwargs: dict[str, Any] = {
            "future": True,
            "connect_args": {"check_same_thread": False},
        }
        if url == "sqlite:///:memory:":
            engine_kwargs["poolclass"] = StaticPool
        self.engine = create_engine(url, **engine_kwargs)
        self._session_factory = sessionmaker(
            self.engine,
            class_=Session,
            expire_on_commit=False,
        )
        # A StaticPool-backed in-memory SQLite database owns one connection.
        # Serialize its transactions so background jobs cannot concurrently use
        # that connection and corrupt transactional state.
        self._session_lock = RLock()
        self._thread_state = local()
        event.listen(self.engine, "connect", self._configure_sqlite)

    @staticmethod
    def _configure_sqlite(dbapi_connection: Any, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        with suppress(Exception):
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()

    @contextmanager
    def session(self) -> Generator[Session]:
        ambient = getattr(self._thread_state, "session", None)
        if isinstance(ambient, Session):
            yield ambient
            return
        with self._session_lock:
            session = self._session_factory()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

    @contextmanager
    def transaction(self) -> Generator[Session]:
        """Batch nested repository calls into one atomic thread-local commit."""

        ambient = getattr(self._thread_state, "session", None)
        if isinstance(ambient, Session):
            yield ambient
            return
        with self._session_lock:
            session = self._session_factory()
            self._thread_state.session = session
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                self._thread_state.session = None
                session.close()

    def ping(self) -> bool:
        with self.session() as session:
            return bool(session.scalar(select(func.count()).select_from(SceneModel)) is not None)

    def recover_interrupted_jobs(self) -> int:
        with self.session() as session:
            jobs = session.scalars(
                select(JobModel).where(JobModel.status.in_(("running", "cancelling")))
            ).all()
            now = utc_now()
            for job in jobs:
                job.status = "failed"
                job.error_code = "runtime_restarted"
                job.error_message = "The local runtime stopped before this job completed."
                job.finished_at = now
                job.stage = "interrupted"
            return len(jobs)


class WorldRepository:
    """Transactional data access with no HTTP concerns."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create_scene(
        self,
        *,
        name: str,
        description: str | None,
        persistence_enabled: bool,
        object_prompts: Sequence[str],
    ) -> SceneModel:
        now = utc_now()
        scene = SceneModel(
            id=uuid7(),
            name=name,
            description=description,
            persistence_enabled=persistence_enabled,
            object_prompts=list(object_prompts),
            coordinate_frame="worldstate_scene_v1",
            created_at=now,
            updated_at=now,
        )
        with self.database.session() as session:
            session.add(scene)
        return scene

    def list_scenes(self) -> list[tuple[SceneModel, int]]:
        with self.database.session() as session:
            count_subquery = (
                select(EntityModel.scene_id, func.count(EntityModel.id).label("entity_count"))
                .group_by(EntityModel.scene_id)
                .subquery()
            )
            rows = session.execute(
                select(SceneModel, func.coalesce(count_subquery.c.entity_count, 0))
                .outerjoin(count_subquery, SceneModel.id == count_subquery.c.scene_id)
                .order_by(SceneModel.created_at.desc())
            ).all()
            return [(scene, int(count)) for scene, count in rows]

    def get_scene(self, scene_id: str) -> tuple[SceneModel, int] | None:
        with self.database.session() as session:
            scene = session.get(SceneModel, scene_id)
            if scene is None:
                return None
            count = session.scalar(
                select(func.count(EntityModel.id)).where(EntityModel.scene_id == scene_id)
            )
            return scene, int(count or 0)

    def update_scene(
        self,
        scene_id: str,
        *,
        name: str | None,
        description: str | None,
        object_prompts: Sequence[str] | None,
        description_was_set: bool,
    ) -> SceneModel | None:
        with self.database.session() as session:
            scene = session.get(SceneModel, scene_id)
            if scene is None:
                return None
            if name is not None:
                scene.name = name
            if description_was_set:
                scene.description = description
            if object_prompts is not None:
                scene.object_prompts = list(object_prompts)
            scene.updated_at = utc_now()
            session.flush()
            session.expunge(scene)
            return scene

    def delete_scene(self, scene_id: str) -> bool:
        with self.database.session() as session:
            scene = session.get(SceneModel, scene_id)
            if scene is None:
                return False
            references = session.scalars(
                select(ArtifactReferenceModel).where(ArtifactReferenceModel.scene_id == scene_id)
            ).all()
            counts: dict[str, int] = {}
            for reference in references:
                counts[reference.artifact_id] = counts.get(reference.artifact_id, 0) + 1
            for artifact_id, count in counts.items():
                artifact = session.get(ArtifactModel, artifact_id)
                if artifact is not None:
                    artifact.ref_count = max(0, artifact.ref_count - count)
            session.delete(scene)
            return True

    def create_capture_session(
        self,
        *,
        scene_id: str,
        mode: str,
        camera: dict[str, object] | None,
        source_name: str | None,
    ) -> CaptureSessionModel | None:
        if self.get_scene(scene_id) is None:
            return None
        capture = CaptureSessionModel(
            id=uuid7(),
            scene_id=scene_id,
            mode=mode,
            status="created",
            camera=camera,
            source_name=source_name,
            started_at=None,
            ended_at=None,
            created_at=utc_now(),
        )
        with self.database.session() as session:
            session.add(capture)
        return capture

    def get_capture_session(self, session_id: str) -> CaptureSessionModel | None:
        with self.database.session() as session:
            capture = session.get(CaptureSessionModel, session_id)
            if capture is not None:
                session.expunge(capture)
            return capture

    def activate_capture_session(self, session_id: str) -> CaptureSessionModel | None:
        with self.database.session() as session:
            capture = session.get(CaptureSessionModel, session_id)
            if capture is None:
                return None
            if capture.status == "created":
                capture.status = "active"
                capture.started_at = utc_now()
            session.flush()
            session.expunge(capture)
            return capture

    def finish_capture_session(
        self,
        session_id: str,
        *,
        status: str = "completed",
    ) -> CaptureSessionModel | None:
        with self.database.session() as session:
            capture = session.get(CaptureSessionModel, session_id)
            if capture is None:
                return None
            capture.status = status
            capture.ended_at = utc_now()
            session.flush()
            session.expunge(capture)
            return capture

    def create_frame(
        self,
        *,
        session_id: str,
        sequence: int,
        captured_at: datetime,
        width: int,
        height: int,
        quality: dict[str, float],
        artifact_id: str | None = None,
        pose: Sequence[float] | None = None,
    ) -> FrameModel:
        frame = FrameModel(
            id=uuid7(),
            session_id=session_id,
            sequence=sequence,
            captured_at=captured_at,
            width=width,
            height=height,
            artifact_id=artifact_id,
            pose=list(pose) if pose is not None else None,
            quality=quality,
            created_at=utc_now(),
        )
        with self.database.session() as session:
            session.add(frame)
            session.flush()
        return frame

    def create_observation(
        self,
        *,
        frame_id: str,
        label: str,
        score: float,
        box_xyxy: Sequence[float],
        position_m: Sequence[float] | None,
        mask_artifact_id: str | None,
        embedding_artifact_id: str | None = None,
        model_run_id: str | None = None,
        covariance: Sequence[float] | None = None,
    ) -> ObservationModel:
        observation = ObservationModel(
            id=uuid7(),
            frame_id=frame_id,
            model_run_id=model_run_id,
            label=label,
            score=score,
            box_xyxy=list(box_xyxy),
            position_m=list(position_m) if position_m is not None else None,
            covariance=list(covariance) if covariance is not None else None,
            mask_artifact_id=mask_artifact_id,
            embedding_artifact_id=embedding_artifact_id,
            created_at=utc_now(),
        )
        with self.database.session() as session:
            session.add(observation)
        return observation

    def create_evidence(
        self,
        *,
        scene_id: str,
        kind: str,
        frame_id: str | None,
        artifact_id: str | None,
        metadata: dict[str, object],
    ) -> EvidenceModel:
        evidence = EvidenceModel(
            id=uuid7(),
            scene_id=scene_id,
            frame_id=frame_id,
            artifact_id=artifact_id,
            kind=kind,
            metadata_json=metadata,
            created_at=utc_now(),
        )
        with self.database.session() as session:
            session.add(evidence)
        return evidence

    def register_artifact(
        self,
        *,
        sha256: str,
        media_type: str,
        kind: str,
        size_bytes: int,
        storage_key: str,
        ref_count: int = 0,
        scene_id: str | None = None,
        session_id: str | None = None,
        job_id: str | None = None,
        purpose: str | None = None,
    ) -> ArtifactModel:
        with self.database.session() as session:
            existing = session.scalar(select(ArtifactModel).where(ArtifactModel.sha256 == sha256))
            if existing is not None:
                existing.ref_count += ref_count
                existing.pending_delete = False
                self._add_artifact_reference(
                    session,
                    artifact=existing,
                    scene_id=scene_id,
                    session_id=session_id,
                    job_id=job_id,
                    purpose=purpose,
                )
                session.flush()
                session.expunge(existing)
                return existing
            artifact = ArtifactModel(
                id=uuid7(),
                sha256=sha256,
                media_type=media_type,
                kind=kind,
                size_bytes=size_bytes,
                storage_key=storage_key,
                ref_count=ref_count,
                pending_delete=False,
                created_at=utc_now(),
            )
            session.add(artifact)
            session.flush()
            self._add_artifact_reference(
                session,
                artifact=artifact,
                scene_id=scene_id,
                session_id=session_id,
                job_id=job_id,
                purpose=purpose,
            )
            session.flush()
            session.expunge(artifact)
            return artifact

    @staticmethod
    def _add_artifact_reference(
        session: Session,
        *,
        artifact: ArtifactModel,
        scene_id: str | None,
        session_id: str | None,
        job_id: str | None,
        purpose: str | None,
    ) -> None:
        owners = (scene_id, session_id, job_id)
        if purpose is None:
            if any(owner is not None for owner in owners):
                raise ValueError("artifact owner requires a purpose")
            return
        if all(owner is None for owner in owners):
            raise ValueError("artifact reference requires an owner")
        existing = session.scalar(
            select(ArtifactReferenceModel).where(
                ArtifactReferenceModel.artifact_id == artifact.id,
                ArtifactReferenceModel.scene_id == scene_id,
                ArtifactReferenceModel.session_id == session_id,
                ArtifactReferenceModel.job_id == job_id,
                ArtifactReferenceModel.purpose == purpose,
            )
        )
        if existing is not None:
            return
        session.add(
            ArtifactReferenceModel(
                id=uuid7(),
                artifact_id=artifact.id,
                scene_id=scene_id,
                session_id=session_id,
                job_id=job_id,
                purpose=purpose,
                created_at=utc_now(),
            )
        )
        artifact.ref_count += 1

    def get_artifact(self, artifact_id: str) -> ArtifactModel | None:
        with self.database.session() as session:
            artifact = session.get(ArtifactModel, artifact_id)
            if artifact is not None:
                session.expunge(artifact)
            return artifact

    def artifact_stats(self) -> tuple[int, int, int]:
        with self.database.session() as session:
            used, count = session.execute(
                select(
                    func.coalesce(func.sum(ArtifactModel.size_bytes), 0),
                    func.count(ArtifactModel.id),
                )
            ).one()
            orphan_count = session.scalar(
                select(func.count(ArtifactModel.id)).where(ArtifactModel.ref_count <= 0)
            )
            return int(used), int(count), int(orphan_count or 0)

    def list_orphan_artifacts(self) -> list[ArtifactModel]:
        with self.database.session() as session:
            artifacts = list(
                session.scalars(select(ArtifactModel).where(ArtifactModel.ref_count <= 0)).all()
            )
            for artifact in artifacts:
                session.expunge(artifact)
            return artifacts

    def delete_artifact_record(self, artifact_id: str) -> bool:
        with self.database.session() as session:
            artifact = session.get(ArtifactModel, artifact_id)
            if artifact is None or artifact.ref_count > 0:
                return False
            session.delete(artifact)
            return True

    def create_job(
        self,
        *,
        kind: str,
        scene_id: str | None,
        session_id: str | None,
        parameters: dict[str, object],
    ) -> JobModel:
        job = JobModel(
            id=uuid7(),
            kind=kind,
            status="queued",
            scene_id=scene_id,
            session_id=session_id,
            parameters=parameters,
            progress=0.0,
            stage="queued",
            result=None,
            error_code=None,
            error_message=None,
            cancellation_requested=False,
            created_at=utc_now(),
            started_at=None,
            finished_at=None,
        )
        with self.database.session() as session:
            session.add(job)
        return job

    def get_job(self, job_id: str) -> JobModel | None:
        with self.database.session() as session:
            job = session.get(JobModel, job_id)
            if job is not None:
                session.expunge(job)
            return job

    def list_jobs(self, *, limit: int = 100) -> list[JobModel]:
        with self.database.session() as session:
            jobs = list(
                session.scalars(
                    select(JobModel).order_by(JobModel.created_at.desc()).limit(limit)
                ).all()
            )
            for job in jobs:
                session.expunge(job)
            return jobs

    def count_pending_jobs(self) -> int:
        with self.database.session() as session:
            value = session.scalar(
                select(func.count(JobModel.id)).where(
                    JobModel.status.in_(("queued", "running", "cancelling"))
                )
            )
            return int(value or 0)

    def update_job(self, job_id: str, **values: object) -> JobModel | None:
        allowed = {
            "status",
            "progress",
            "stage",
            "result",
            "error_code",
            "error_message",
            "cancellation_requested",
            "started_at",
            "finished_at",
        }
        if unknown := set(values) - allowed:
            raise ValueError(f"unsupported job fields: {sorted(unknown)}")
        with self.database.session() as session:
            job = session.get(JobModel, job_id)
            if job is None:
                return None
            for key, value in values.items():
                setattr(job, key, value)
            session.flush()
            session.expunge(job)
            return job

    def list_entities(self, scene_id: str, *, at: datetime | None = None) -> list[EntityModel]:
        with self.database.session() as session:
            statement = select(EntityModel).where(EntityModel.scene_id == scene_id)
            if at is not None:
                statement = statement.where(EntityModel.created_at <= at)
            entities = list(session.scalars(statement.order_by(EntityModel.created_at)).all())
            for entity in entities:
                session.expunge(entity)
            return entities

    def get_entity(self, entity_id: str) -> EntityModel | None:
        with self.database.session() as session:
            entity = session.get(EntityModel, entity_id)
            if entity is not None:
                session.expunge(entity)
            return entity

    def update_entity_label(self, entity_id: str, label: str) -> EntityModel | None:
        normalized = " ".join(label.split()).strip()
        if not normalized or len(normalized) > 160:
            raise ValueError("entity label must contain 1 to 160 characters")
        with self.database.session() as session:
            entity = session.get(EntityModel, entity_id)
            if entity is None:
                return None
            entity.canonical_label = normalized
            entity.display_name = normalized
            session.flush()
            session.expunge(entity)
            return entity

    def create_entity(
        self,
        *,
        scene_id: str,
        label: str,
        layer: str,
        observed_at: datetime,
    ) -> EntityModel:
        entity = EntityModel(
            id=uuid7(),
            scene_id=scene_id,
            canonical_label=label,
            display_name=label,
            layer=layer,
            status="visible",
            created_at=observed_at,
            last_seen_at=observed_at,
        )
        with self.database.session() as session:
            session.add(entity)
        return entity

    def get_current_state(
        self, entity_id: str, *, at: datetime | None = None
    ) -> EntityStateModel | None:
        with self.database.session() as session:
            statement = select(EntityStateModel).where(EntityStateModel.entity_id == entity_id)
            if at is None:
                statement = statement.where(EntityStateModel.valid_to.is_(None))
            else:
                statement = statement.where(
                    EntityStateModel.valid_from <= at,
                    (EntityStateModel.valid_to.is_(None)) | (EntityStateModel.valid_to > at),
                )
            state = session.scalar(statement.order_by(EntityStateModel.valid_from.desc()))
            if state is not None:
                session.expunge(state)
            return state

    def list_current_states(self, scene_id: str) -> dict[str, EntityStateModel]:
        """Load one active state per scene entity in a single query."""

        with self.database.session() as session:
            states = list(
                session.scalars(
                    select(EntityStateModel)
                    .join(EntityModel, EntityModel.id == EntityStateModel.entity_id)
                    .where(
                        EntityModel.scene_id == scene_id,
                        EntityStateModel.valid_to.is_(None),
                    )
                ).all()
            )
            result = {state.entity_id: state for state in states}
            for state in states:
                session.expunge(state)
            return result

    def list_entity_states(self, entity_id: str) -> list[EntityStateModel]:
        with self.database.session() as session:
            states = list(
                session.scalars(
                    select(EntityStateModel)
                    .where(EntityStateModel.entity_id == entity_id)
                    .order_by(EntityStateModel.valid_from)
                ).all()
            )
            for state in states:
                session.expunge(state)
            return states

    def append_entity_state(
        self,
        *,
        entity_id: str,
        valid_from: datetime,
        presence: str,
        confidence: float,
        uncertainty: float,
        position_m: Sequence[float] | None,
        quaternion_xyzw: Sequence[float] | None,
        bounds_m: Sequence[float] | None,
        box_xyxy: Sequence[float] | None,
        evidence_ids: Sequence[str],
    ) -> EntityStateModel:
        with self.database.session() as session:
            session.execute(
                update(EntityStateModel)
                .where(
                    EntityStateModel.entity_id == entity_id,
                    EntityStateModel.valid_to.is_(None),
                )
                .values(valid_to=valid_from)
                .execution_options(synchronize_session=False)
            )
            state = EntityStateModel(
                id=uuid7(),
                entity_id=entity_id,
                valid_from=valid_from,
                valid_to=None,
                presence=presence,
                confidence=confidence,
                uncertainty=uncertainty,
                position_m=list(position_m) if position_m is not None else None,
                quaternion_xyzw=(list(quaternion_xyzw) if quaternion_xyzw is not None else None),
                bounds_m=list(bounds_m) if bounds_m is not None else None,
                box_xyxy=list(box_xyxy) if box_xyxy is not None else None,
                evidence_ids=list(evidence_ids),
            )
            session.add(state)
            entity_values: dict[str, object] = {"status": presence}
            if presence in {"visible", "rediscovered"}:
                entity_values["last_seen_at"] = valid_from
            session.execute(
                update(EntityModel)
                .where(EntityModel.id == entity_id)
                .values(**entity_values)
                .execution_options(synchronize_session=False)
            )
            session.flush()
            session.expunge(state)
            return state

    def create_event(
        self,
        *,
        scene_id: str,
        entity_id: str,
        kind: str,
        occurred_at: datetime,
        confidence: float,
        evidence_ids: Sequence[str],
        payload: dict[str, object] | None = None,
    ) -> WorldEventModel:
        event_model = WorldEventModel(
            id=uuid7(),
            scene_id=scene_id,
            entity_id=entity_id,
            kind=kind,
            occurred_at=occurred_at,
            confidence=confidence,
            evidence_ids=list(evidence_ids),
            payload=payload or {},
        )
        with self.database.session() as session:
            session.add(event_model)
        return event_model

    def list_events(
        self,
        scene_id: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 500,
    ) -> list[WorldEventModel]:
        with self.database.session() as session:
            statement = select(WorldEventModel).where(WorldEventModel.scene_id == scene_id)
            if since is not None:
                statement = statement.where(WorldEventModel.occurred_at >= since)
            if until is not None:
                statement = statement.where(WorldEventModel.occurred_at <= until)
            events = list(
                session.scalars(
                    statement.order_by(WorldEventModel.occurred_at.desc()).limit(limit)
                ).all()
            )
            for event_model in events:
                session.expunge(event_model)
            return events

    def list_relationships(
        self,
        scene_id: str,
        *,
        at: datetime | None = None,
    ) -> list[RelationshipModel]:
        with self.database.session() as session:
            statement = select(RelationshipModel).where(RelationshipModel.scene_id == scene_id)
            if at is None:
                statement = statement.where(RelationshipModel.valid_to.is_(None))
            else:
                statement = statement.where(
                    RelationshipModel.valid_from <= at,
                    (RelationshipModel.valid_to.is_(None)) | (RelationshipModel.valid_to > at),
                )
            rows = list(session.scalars(statement).all())
            for row in rows:
                session.expunge(row)
            return rows

    def replace_relationships(
        self,
        *,
        scene_id: str,
        observed_at: datetime,
        relationships: Sequence[tuple[str, str, str, float]],
    ) -> list[RelationshipModel]:
        with self.database.session() as session:
            active = session.scalars(
                select(RelationshipModel).where(
                    RelationshipModel.scene_id == scene_id,
                    RelationshipModel.valid_to.is_(None),
                )
            ).all()
            active_by_key = {
                (
                    relationship.subject_entity_id,
                    relationship.object_entity_id,
                    relationship.kind,
                ): relationship
                for relationship in active
            }
            incoming_by_key = {
                (subject_id, object_id, kind): confidence
                for subject_id, object_id, kind, confidence in relationships
            }
            if active_by_key.keys() == incoming_by_key.keys() and all(
                abs(active_by_key[key].confidence - confidence) < 0.025
                for key, confidence in incoming_by_key.items()
            ):
                # A relationship is a validity interval, not a per-frame log.
                # Keep the interval open while topology and confidence are
                # materially unchanged; otherwise a static desk produces a
                # quadratic stream of duplicate rows at checkpoint cadence.
                unchanged = list(active_by_key.values())
                for relationship in unchanged:
                    session.expunge(relationship)
                return unchanged
            for relationship in active:
                relationship.valid_to = observed_at
            created: list[RelationshipModel] = []
            for subject_id, object_id, kind, confidence in relationships:
                relationship = RelationshipModel(
                    id=uuid7(),
                    scene_id=scene_id,
                    subject_entity_id=subject_id,
                    object_entity_id=object_id,
                    kind=kind,
                    confidence=confidence,
                    valid_from=observed_at,
                    valid_to=None,
                )
                session.add(relationship)
                created.append(relationship)
            session.flush()
            for relationship in created:
                session.expunge(relationship)
            return created
