"""Content-addressed artifact storage with quota and traversal protection."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from worldstate_api.persistence import ArtifactModel, WorldRepository

_STORAGE_KEY = re.compile(r"^sha256/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}$")


class ArtifactError(RuntimeError):
    pass


class StorageQuotaExceeded(ArtifactError):
    pass


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    id: str
    sha256: str
    media_type: str
    kind: str
    size_bytes: int


class ArtifactStore:
    """Store immutable blobs outside the web root and expose opaque IDs."""

    def __init__(
        self,
        *,
        root: Path,
        quota_bytes: int,
        repository: WorldRepository,
    ) -> None:
        self.root = root.resolve()
        self.quota_bytes = quota_bytes
        self.repository = repository
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, storage_key: str) -> Path:
        if not _STORAGE_KEY.fullmatch(storage_key):
            raise ArtifactError("invalid artifact storage key")
        candidate = (self.root / Path(storage_key)).resolve()
        if self.root not in candidate.parents:
            raise ArtifactError("artifact path escapes the store")
        return candidate

    @staticmethod
    def _storage_key(digest: str) -> str:
        return f"sha256/{digest[:2]}/{digest[2:4]}/{digest}"

    def _check_quota(self, incoming_bytes: int) -> None:
        used, _, _ = self.repository.artifact_stats()
        if used + incoming_bytes > self.quota_bytes:
            raise StorageQuotaExceeded("artifact storage quota would be exceeded")

    def put_bytes(
        self,
        payload: bytes,
        *,
        media_type: str,
        kind: str,
        ref_count: int = 0,
        scene_id: str | None = None,
        session_id: str | None = None,
        job_id: str | None = None,
        purpose: str | None = None,
    ) -> StoredArtifact:
        return self.put_chunks(
            (payload,),
            media_type=media_type,
            kind=kind,
            maximum_bytes=len(payload),
            ref_count=ref_count,
            scene_id=scene_id,
            session_id=session_id,
            job_id=job_id,
            purpose=purpose,
        )

    def put_chunks(
        self,
        chunks: Iterable[bytes],
        *,
        media_type: str,
        kind: str,
        maximum_bytes: int,
        ref_count: int = 0,
        scene_id: str | None = None,
        session_id: str | None = None,
        job_id: str | None = None,
        purpose: str | None = None,
    ) -> StoredArtifact:
        """Hash and atomically store a bounded stream."""

        if maximum_bytes <= 0:
            raise ValueError("maximum_bytes must be positive")
        digest = hashlib.sha256()
        size = 0
        temporary_path: Path | None = None
        created_final_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".incoming-",
                dir=self.root,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                for chunk in chunks:
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > maximum_bytes:
                        raise ArtifactError("artifact exceeds the configured size limit")
                    digest.update(chunk)
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())

            if size == 0:
                raise ArtifactError("empty artifacts are not accepted")
            hex_digest = digest.hexdigest()
            storage_key = self._storage_key(hex_digest)
            final_path = self._path_for_key(storage_key)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            if final_path.exists():
                temporary_path.unlink(missing_ok=True)
            else:
                self._check_quota(size)
                temporary_path.replace(final_path)
                created_final_path = final_path
            record = self.repository.register_artifact(
                sha256=hex_digest,
                media_type=media_type,
                kind=kind,
                size_bytes=size,
                storage_key=storage_key,
                ref_count=ref_count,
                scene_id=scene_id,
                session_id=session_id,
                job_id=job_id,
                purpose=purpose,
            )
            return self._public(record)
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            if created_final_path is not None:
                created_final_path.unlink(missing_ok=True)
            raise

    def read_bytes(self, artifact_id: str, *, maximum_bytes: int | None = None) -> bytes:
        record = self.repository.get_artifact(artifact_id)
        if record is None or record.pending_delete:
            raise FileNotFoundError("artifact does not exist")
        if maximum_bytes is not None and record.size_bytes > maximum_bytes:
            raise ArtifactError("artifact exceeds the requested read limit")
        path = self._path_for_key(record.storage_key)
        payload = path.read_bytes()
        if len(payload) != record.size_bytes:
            raise ArtifactError("artifact size does not match its database record")
        if hashlib.sha256(payload).hexdigest() != record.sha256:
            raise ArtifactError("artifact integrity check failed")
        return payload

    def resolve_trusted_path(self, artifact_id: str) -> Path:
        """Resolve an internal path after database and containment checks."""

        record = self.repository.get_artifact(artifact_id)
        if record is None or record.pending_delete:
            raise FileNotFoundError("artifact does not exist")
        path = self._path_for_key(record.storage_key)
        if not path.is_file():
            raise FileNotFoundError("artifact bytes are missing")
        return path

    def collect_orphans(self) -> tuple[int, int]:
        removed = 0
        reclaimed = 0
        for record in self.repository.list_orphan_artifacts():
            path = self._path_for_key(record.storage_key)
            if path.exists():
                size = path.stat().st_size
                path.unlink()
                reclaimed += size
            if self.repository.delete_artifact_record(record.id):
                removed += 1
        return removed, reclaimed

    @staticmethod
    def _public(record: ArtifactModel) -> StoredArtifact:
        return StoredArtifact(
            id=record.id,
            sha256=record.sha256,
            media_type=record.media_type,
            kind=record.kind,
            size_bytes=record.size_bytes,
        )
