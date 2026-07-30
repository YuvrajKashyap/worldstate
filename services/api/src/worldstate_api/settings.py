"""Validated runtime settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    environment: str = Field(default="development", alias="WORLDSTATE_ENVIRONMENT")
    host: str = Field(default="127.0.0.1", alias="WORLDSTATE_HOST")
    port: int = Field(default=8000, alias="WORLDSTATE_PORT", ge=1, le=65_535)
    allowed_origins_csv: str = Field(
        default="http://127.0.0.1:5173,http://localhost:5173",
        alias="WORLDSTATE_ALLOWED_ORIGINS",
    )
    persistence_enabled: bool = Field(
        default=False,
        alias="WORLDSTATE_PERSISTENCE_ENABLED",
    )

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        origins = tuple(
            origin.strip() for origin in self.allowed_origins_csv.split(",") if origin.strip()
        )
        if not origins:
            raise ValueError("at least one allowed origin is required")
        if "*" in origins:
            raise ValueError("wildcard origins are not permitted")
        return origins
