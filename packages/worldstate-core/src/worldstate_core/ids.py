"""Opaque, time-sortable public identifiers."""

from __future__ import annotations

import secrets
import time
from uuid import UUID


def uuid7(now_ms: int | None = None) -> str:
    """Return a UUIDv7 string using cryptographically secure random bits."""

    timestamp_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if not 0 <= timestamp_ms < 2**48:
        raise ValueError("UUIDv7 timestamp must fit in 48 bits")

    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (timestamp_ms << 80) | (0b0111 << 76) | (random_a << 64) | (0b10 << 62) | random_b
    return str(UUID(int=value))
