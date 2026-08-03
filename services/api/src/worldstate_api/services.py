"""Application service container and built-in job handlers."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import cast

from worldstate_api.artifacts import ArtifactStore
from worldstate_api.contracts import CapabilityState
from worldstate_api.evaluation import (
    evaluate_manifest,
    provenance,
    write_parquet_if_available,
)
from worldstate_api.geometry import ScanPipeline
from worldstate_api.jobs import JobContext, JobManager
from worldstate_api.persistence import Database, WorldRepository
from worldstate_api.providers.registry import ModelRegistry
from worldstate_api.runtime import GpuScheduler, ProviderFactory
from worldstate_api.security import SessionRegistry, SlidingWindowRateLimiter
from worldstate_api.settings import Settings
from worldstate_api.world_engine import WorldEngine


class AppServices:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._temporary_data: tempfile.TemporaryDirectory[str] | None = None
        if settings.environment == "test" and settings.data_root == Path(".worldstate"):
            self._temporary_data = tempfile.TemporaryDirectory(prefix="worldstate-test-")
            settings.data_root = Path(self._temporary_data.name)
        if settings.persistence_enabled:
            (settings.data_root / "db").mkdir(parents=True, exist_ok=True)
        settings.upload_root.mkdir(parents=True, exist_ok=True)
        settings.export_root.mkdir(parents=True, exist_ok=True)

        self.database = Database(settings.database_url)
        self.database.create_schema()
        self.database.recover_interrupted_jobs()
        self.repository = WorldRepository(self.database)
        self.artifacts = ArtifactStore(
            root=settings.artifact_root,
            quota_bytes=settings.storage_quota_bytes,
            repository=self.repository,
        )
        self.sessions = SessionRegistry(
            bootstrap_token=settings.bootstrap_token,
            ttl_seconds=settings.session_ttl_seconds,
        )
        self.bootstrap_limiter = SlidingWindowRateLimiter(limit=10, window_seconds=60.0)
        self.model_registry = ModelRegistry(
            manifest_path=settings.model_manifest_path,
            lock_path=settings.model_lock_path,
            models_root=settings.models_root,
        )
        self.scheduler = GpuScheduler()
        self.providers = ProviderFactory(
            mode=settings.provider_mode,
            registry=self.model_registry,
        )
        self.world_engine = WorldEngine(
            repository=self.repository,
            artifact_store=self.artifacts,
        )
        self.jobs = JobManager(
            repository=self.repository,
            maximum_pending=settings.max_pending_jobs,
        )
        self.scan_pipeline = ScanPipeline(
            artifact_store=self.artifacts,
            model_registry=self.model_registry,
            scheduler=self.scheduler,
            work_root=settings.data_root / "work",
            maximum_duration_seconds=settings.max_video_duration_seconds,
            suspend_live_provider=self.providers.suspend,
            resume_live_provider=self.providers.warmup,
        )
        self.jobs.register("scan", self.scan_pipeline.run)
        self.jobs.register("reconstruction", self.scan_pipeline.run)
        self.jobs.register("evaluation", self._evaluate)
        self.jobs.register("export", self._export)
        self.jobs.register("garbage_collection", self._garbage_collect)

    def capability_states(self) -> dict[str, CapabilityState]:
        models = {
            item.id: item.state.value
            for item in self.model_registry.list_models(verify_checksums=False)
        }
        required_live = (
            "grounding-dino-tiny",
            "sam2.1-hiera-tiny",
            "dinov2-small",
            "depth-anything-v2-small",
        )
        learned_live_ready = all(models.get(model) == "available" for model in required_live)
        geometry_ready = models.get("map-anything-apache") == "available"
        return {
            "live_replay": CapabilityState.READY,
            "live_classical": CapabilityState.READY,
            "live_learned": (
                CapabilityState.READY if learned_live_ready else CapabilityState.UNAVAILABLE
            ),
            "temporal_memory": CapabilityState.READY,
            "persistence": (
                CapabilityState.READY
                if self.settings.persistence_enabled
                else CapabilityState.DEGRADED
            ),
            "scan": (CapabilityState.READY if geometry_ready else CapabilityState.DEGRADED),
            "evaluation": CapabilityState.READY,
            "export": CapabilityState.READY,
        }

    def _evaluate(self, context: JobContext) -> dict[str, object]:
        context.update(progress=0.10, stage="loading_manifest")
        inline_manifest = context.parameters.get("manifest")
        if isinstance(inline_manifest, dict):
            manifest_bytes = json.dumps(
                inline_manifest,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        else:
            manifest_id = str(context.parameters.get("manifest_artifact_id", ""))
            if not manifest_id:
                raise ValueError("evaluation requires manifest or manifest_artifact_id")
            manifest_bytes = self.artifacts.read_bytes(
                manifest_id,
                maximum_bytes=25_000_000,
            )
        dataset_hash = hashlib.sha256(manifest_bytes).hexdigest()
        payload_object: object = json.loads(manifest_bytes)
        if not isinstance(payload_object, dict):
            raise ValueError("evaluation manifest must be a JSON object")
        payload = cast(dict[str, object], payload_object)
        context.update(progress=0.45, stage="computing_metrics")
        metrics = evaluate_manifest(payload)
        context.check_cancelled()
        output = {
            "schema_version": 1,
            "metrics": metrics,
            "provenance": provenance(
                config=context.parameters,
                dataset_hash=dataset_hash,
            ),
        }
        result = self.artifacts.put_bytes(
            json.dumps(output, indent=2, sort_keys=True).encode(),
            media_type="application/json",
            kind="evaluation-result",
            job_id=context.job_id,
            purpose="evaluation-result",
        )
        parquet_artifact_id: str | None = None
        with tempfile.TemporaryDirectory(
            prefix="evaluation-",
            dir=self.settings.data_root / "work",
        ) as directory:
            parquet_path = Path(directory) / "results.parquet"
            if write_parquet_if_available(
                [
                    {
                        "schema_version": 1,
                        "dataset_hash": dataset_hash,
                        "metrics_json": json.dumps(metrics, sort_keys=True),
                    }
                ],
                parquet_path,
            ):
                parquet = self.artifacts.put_bytes(
                    parquet_path.read_bytes(),
                    media_type="application/vnd.apache.parquet",
                    kind="evaluation-result-parquet",
                    job_id=context.job_id,
                    purpose="evaluation-result-parquet",
                )
                parquet_artifact_id = parquet.id
        context.update(progress=0.95, stage="writing_results")
        return {
            "result_artifact_id": result.id,
            "parquet_artifact_id": parquet_artifact_id,
            **metrics,
        }

    def _export(self, context: JobContext) -> dict[str, object]:
        if context.scene_id is None:
            raise ValueError("export jobs require a scene")
        scene_row = self.repository.get_scene(context.scene_id)
        if scene_row is None:
            raise ValueError("scene does not exist")
        scene, entity_count = scene_row
        context.update(progress=0.15, stage="serializing_scene")
        entities = self.repository.list_entities(scene.id)
        events = self.repository.list_events(scene.id, limit=100_000)
        relationships = self.repository.list_relationships(scene.id)
        manifest = {
            "schema_version": 1,
            "scene": {
                "id": scene.id,
                "name": scene.name,
                "description": scene.description,
                "coordinate_frame": scene.coordinate_frame,
                "created_at": scene.created_at.isoformat(),
                "entity_count": entity_count,
            },
            "entities": [
                {
                    "id": entity.id,
                    "label": entity.canonical_label,
                    "display_name": entity.display_name,
                    "layer": entity.layer,
                    "status": entity.status,
                    "created_at": entity.created_at.isoformat(),
                    "last_seen_at": (
                        entity.last_seen_at.isoformat() if entity.last_seen_at else None
                    ),
                    "states": [
                        {
                            "id": state.id,
                            "valid_from": state.valid_from.isoformat(),
                            "valid_to": state.valid_to.isoformat() if state.valid_to else None,
                            "presence": state.presence,
                            "confidence": state.confidence,
                            "uncertainty": state.uncertainty,
                            "position_m": state.position_m,
                            "quaternion_xyzw": state.quaternion_xyzw,
                            "bounds_m": state.bounds_m,
                        }
                        for state in self.repository.list_entity_states(entity.id)
                    ],
                }
                for entity in entities
            ],
            "events": [
                {
                    "id": event.id,
                    "entity_id": event.entity_id,
                    "kind": event.kind,
                    "occurred_at": event.occurred_at.isoformat(),
                    "confidence": event.confidence,
                    "evidence_ids": event.evidence_ids,
                    "payload": event.payload,
                }
                for event in events
            ],
            "relationships": [
                {
                    "id": relationship.id,
                    "subject_entity_id": relationship.subject_entity_id,
                    "object_entity_id": relationship.object_entity_id,
                    "kind": relationship.kind,
                    "confidence": relationship.confidence,
                    "valid_from": relationship.valid_from.isoformat(),
                    "valid_to": (
                        relationship.valid_to.isoformat() if relationship.valid_to else None
                    ),
                }
                for relationship in relationships
            ],
        }
        context.update(progress=0.75, stage="writing_manifest")
        artifact = self.artifacts.put_bytes(
            json.dumps(manifest, indent=2, sort_keys=True).encode(),
            media_type="application/json",
            kind="scene-export",
            scene_id=scene.id,
            job_id=context.job_id,
            purpose="scene-export",
        )
        return {"artifact_ids": [artifact.id], "formats": ["manifest"]}

    def _garbage_collect(self, context: JobContext) -> dict[str, object]:
        context.update(progress=0.25, stage="finding_orphans")
        removed, reclaimed = self.artifacts.collect_orphans()
        return {"removed_artifacts": removed, "reclaimed_bytes": reclaimed}

    def close(self) -> None:
        self.jobs.close()
        self.scheduler.close()
        self.providers.close()
        self.database.dispose()
        if self._temporary_data is not None:
            self._temporary_data.cleanup()


def resolve_repo_path(path: Path) -> Path:
    """Resolve a repository-relative configuration path without exposing it."""

    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()
