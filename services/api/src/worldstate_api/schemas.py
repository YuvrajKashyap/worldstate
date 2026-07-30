"""Versioned public response schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictResponse):
    status: Literal["ok"]
    service: Literal["worldstate-api"]
    version: str


class SystemResponse(StrictResponse):
    environment: str
    persistence_enabled: bool
    protocol_version: Literal["v1"]
    product_phase: Literal["foundation"]
