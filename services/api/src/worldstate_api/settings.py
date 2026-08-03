"""Validated, secure-by-default runtime settings."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_root() -> Path:
    return Path(".worldstate")


class Settings(BaseSettings):
    """Environment-backed application settings.

    Paths remain server-internal and are never serialized through public
    response models.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
        validate_assignment=True,
    )

    environment: Literal["development", "test", "production"] = Field(
        default="development",
        alias="WORLDSTATE_ENVIRONMENT",
    )
    host: str = Field(default="127.0.0.1", alias="WORLDSTATE_HOST")
    port: int = Field(default=8000, alias="WORLDSTATE_PORT", ge=1, le=65_535)
    allowed_origins_csv: str = Field(
        default="http://127.0.0.1:5173,http://localhost:5173",
        alias="WORLDSTATE_ALLOWED_ORIGINS",
    )
    allowed_hosts_csv: str = Field(
        default="127.0.0.1,localhost,testserver",
        alias="WORLDSTATE_ALLOWED_HOSTS",
    )
    persistence_enabled: bool = Field(
        default=False,
        alias="WORLDSTATE_PERSISTENCE_ENABLED",
    )
    data_root: Path = Field(default_factory=_default_data_root, alias="WORLDSTATE_DATA_ROOT")
    database_url_override: str | None = Field(
        default=None,
        alias="WORLDSTATE_DATABASE_URL",
    )
    frontend_dist: Path = Field(
        default=Path("apps/web/dist"),
        alias="WORLDSTATE_FRONTEND_DIST",
    )
    model_manifest_path: Path = Field(
        default=Path("configs/models.yaml"),
        alias="WORLDSTATE_MODEL_MANIFEST",
    )
    model_lock_path_override: Path | None = Field(
        default=None,
        alias="WORLDSTATE_MODEL_LOCK",
    )
    bootstrap_token: str | None = Field(default=None, alias="WORLDSTATE_BOOTSTRAP_TOKEN")
    session_ttl_seconds: int = Field(
        default=43_200,
        alias="WORLDSTATE_SESSION_TTL_SECONDS",
        ge=300,
        le=86_400,
    )
    secure_cookies: bool = Field(default=False, alias="WORLDSTATE_SECURE_COOKIES")
    max_frame_bytes: int = Field(
        default=2_500_000,
        alias="WORLDSTATE_MAX_FRAME_BYTES",
        ge=64_000,
        le=20_000_000,
    )
    max_frame_width: int = Field(
        default=1920,
        alias="WORLDSTATE_MAX_FRAME_WIDTH",
        ge=320,
        le=7680,
    )
    max_frame_height: int = Field(
        default=1080,
        alias="WORLDSTATE_MAX_FRAME_HEIGHT",
        ge=240,
        le=4320,
    )
    max_upload_bytes: int = Field(
        default=2_147_483_648,
        alias="WORLDSTATE_MAX_UPLOAD_BYTES",
        ge=1_048_576,
        le=8_589_934_592,
    )
    max_video_duration_seconds: int = Field(
        default=1_800,
        alias="WORLDSTATE_MAX_VIDEO_DURATION_SECONDS",
        ge=1,
        le=7_200,
    )
    storage_quota_bytes: int = Field(
        default=75_000_000_000,
        alias="WORLDSTATE_STORAGE_QUOTA_BYTES",
        ge=1_000_000_000,
        le=1_000_000_000_000,
    )
    max_pending_jobs: int = Field(
        default=16,
        alias="WORLDSTATE_MAX_PENDING_JOBS",
        ge=1,
        le=128,
    )
    max_prompts: int = Field(
        default=32,
        alias="WORLDSTATE_MAX_PROMPTS",
        ge=1,
        le=128,
    )
    provider_mode: Literal["replay", "classical", "models"] = Field(
        default="replay",
        alias="WORLDSTATE_PROVIDER_MODE",
    )
    log_level: str = Field(default="INFO", alias="WORLDSTATE_LOG_LEVEL")

    @field_validator("host")
    @classmethod
    def require_loopback(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("WorldState must bind to a loopback address")
        return value

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        origins = tuple(
            origin.strip() for origin in self.allowed_origins_csv.split(",") if origin.strip()
        )
        if not origins:
            raise ValueError("at least one allowed origin is required")
        if "*" in origins:
            raise ValueError("wildcard origins are not permitted")
        if any(
            not origin.startswith(("http://localhost", "http://127.0.0.1")) for origin in origins
        ):
            raise ValueError("only local browser origins are permitted")
        return origins

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        hosts = tuple(host.strip() for host in self.allowed_hosts_csv.split(",") if host.strip())
        if not hosts or "*" in hosts:
            raise ValueError("an explicit host allowlist is required")
        return hosts

    @cached_property
    def database_url(self) -> str:
        if self.database_url_override:
            if self.database_url_override == "sqlite:///:memory:":
                return self.database_url_override
            if not self.database_url_override.startswith("sqlite:///"):
                raise ValueError("WorldState currently supports local SQLite databases only")
            return self.database_url_override
        if not self.persistence_enabled:
            return "sqlite:///:memory:"
        database_path = (self.data_root / "db" / "worldstate.sqlite3").resolve()
        return f"sqlite:///{database_path.as_posix()}"

    @property
    def artifact_root(self) -> Path:
        return self.data_root / "artifacts"

    @property
    def upload_root(self) -> Path:
        return self.data_root / "uploads"

    @property
    def export_root(self) -> Path:
        return self.data_root / "exports"

    @property
    def models_root(self) -> Path:
        return self.data_root / "models"

    @property
    def model_lock_path(self) -> Path:
        return self.model_lock_path_override or self.data_root / "models.lock.json"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"
