"""Allowlisted, revision-pinned model inventory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from worldstate_api.contracts import ModelInfo, ModelState

_HASH_CHUNK_BYTES = 8 * 1024 * 1024


class ModelManifestError(RuntimeError):
    pass


class ManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    capability: str
    license: str
    source: str
    revision: str
    relative_path: str
    required: bool = False
    gated: bool = False
    approximate_size_bytes: int | None = None


class ManifestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    models: tuple[ManifestEntry, ...]


class LockEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: str
    files: dict[str, str]


class LockPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    models: dict[str, LockEntry]


@dataclass(frozen=True, slots=True)
class ModelSpec:
    id: str
    display_name: str
    capability: str
    license: str
    source: str
    revision: str
    relative_path: str
    required: bool
    gated: bool
    approximate_size_bytes: int | None


class ModelRegistry:
    def __init__(self, *, manifest_path: Path, lock_path: Path, models_root: Path) -> None:
        self.manifest_path = manifest_path
        self.lock_path = lock_path
        self.models_root = models_root.resolve()
        self.models_root.mkdir(parents=True, exist_ok=True)
        self._specs = self._load_manifest()

    def _load_manifest(self) -> tuple[ModelSpec, ...]:
        if not self.manifest_path.is_file():
            return ()
        raw_payload: object = yaml.safe_load(self.manifest_path.read_text(encoding="utf-8"))
        try:
            payload = ManifestPayload.model_validate(raw_payload)
        except Exception as error:
            raise ModelManifestError("model manifest does not match schema version 1") from error
        specs = tuple(
            ModelSpec(
                id=entry.id,
                display_name=entry.display_name,
                capability=entry.capability,
                license=entry.license,
                source=entry.source,
                revision=entry.revision,
                relative_path=entry.relative_path,
                required=entry.required,
                gated=entry.gated,
                approximate_size_bytes=entry.approximate_size_bytes,
            )
            for entry in payload.models
        )
        for spec in specs:
            if spec.revision in {"", "main", "master", "latest"}:
                raise ModelManifestError(f"model {spec.id} does not pin an immutable revision")
            self._resolve_model_path(spec)
        if len({spec.id for spec in specs}) != len(specs):
            raise ModelManifestError("model manifest IDs must be unique")
        return specs

    @staticmethod
    def hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(_HASH_CHUNK_BYTES):
                digest.update(chunk)
        return digest.hexdigest()

    def _resolve_model_path(self, spec: ModelSpec) -> Path:
        candidate = (self.models_root / spec.relative_path).resolve()
        if self.models_root != candidate and self.models_root not in candidate.parents:
            raise ModelManifestError(f"model {spec.id} path escapes the models root")
        return candidate

    def _lock_entries(self) -> dict[str, LockEntry]:
        if not self.lock_path.is_file():
            return {}
        raw_payload: object = json.loads(self.lock_path.read_text(encoding="utf-8"))
        try:
            return LockPayload.model_validate(raw_payload).models
        except Exception as error:
            raise ModelManifestError("model lock does not match schema version 1") from error

    def _verified_files(
        self,
        spec: ModelSpec,
    ) -> tuple[Path, LockEntry, tuple[tuple[str, int, int, int, int, int], ...]] | None:
        model_path = self._resolve_model_path(spec)
        if not model_path.exists():
            return None
        entry = self._lock_entries().get(spec.id)
        if entry is None or entry.revision != spec.revision or not entry.files:
            return model_path, LockEntry(revision="", files={}), ()
        signature: list[tuple[str, int, int, int, int, int]] = []
        for relative_name in entry.files:
            file_path = (model_path / relative_name).resolve()
            if model_path not in file_path.parents or not file_path.is_file():
                return model_path, entry, ()
            stat = file_path.stat()
            signature.append(
                (
                    relative_name,
                    stat.st_size,
                    stat.st_mtime_ns,
                    stat.st_ctime_ns,
                    stat.st_dev,
                    stat.st_ino,
                )
            )
        return model_path, entry, tuple(signature)

    def quick_state(self, spec: ModelSpec) -> ModelState:
        """Inspect the immutable lock and file set without reading model bytes."""

        verified = self._verified_files(spec)
        if verified is None:
            return ModelState.NOT_INSTALLED
        _model_path, entry, signature = verified
        if entry.revision != spec.revision or not signature:
            return ModelState.INVALID
        return ModelState.AVAILABLE

    def verify(self, spec: ModelSpec) -> ModelState:
        verified = self._verified_files(spec)
        if verified is None:
            return ModelState.NOT_INSTALLED
        model_path, entry, signature = verified
        if entry.revision != spec.revision or not signature:
            return ModelState.INVALID
        state = ModelState.AVAILABLE
        for relative_name, expected_digest in entry.files.items():
            file_path = (model_path / relative_name).resolve()
            digest = self.hash_file(file_path)
            if digest != expected_digest:
                state = ModelState.INVALID
                break
        return state

    def list_models(self, *, verify_checksums: bool = True) -> tuple[ModelInfo, ...]:
        state_for = self.verify if verify_checksums else self.quick_state
        return tuple(
            ModelInfo(
                id=spec.id,
                display_name=spec.display_name,
                capability=spec.capability,
                license=spec.license,
                source=spec.source,
                revision=spec.revision,
                state=state_for(spec),
                required=spec.required,
                gated=spec.gated,
                approximate_size_bytes=spec.approximate_size_bytes,
            )
            for spec in self._specs
        )

    def specs(self) -> tuple[ModelSpec, ...]:
        return self._specs

    def get_spec(self, model_id: str) -> ModelSpec:
        for spec in self._specs:
            if spec.id == model_id:
                return spec
        raise KeyError(model_id)

    def trusted_path(self, model_id: str) -> Path:
        spec = self.get_spec(model_id)
        if self.verify(spec) is not ModelState.AVAILABLE:
            raise ModelManifestError(f"model {model_id} is not installed and verified")
        return self._resolve_model_path(spec)
