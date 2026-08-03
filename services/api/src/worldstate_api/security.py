"""Local capability sessions, CSRF protection, and browser boundary controls."""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, WebSocket, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from worldstate_api.settings import Settings

SESSION_COOKIE = "worldstate_session"
CSRF_HEADER = "X-WorldState-CSRF"


@dataclass(frozen=True, slots=True)
class SessionPrincipal:
    token: str
    csrf_token: str
    expires_at: datetime


class SessionRegistry:
    """Short-lived in-memory sessions bootstrapped by a one-time launcher secret."""

    def __init__(self, *, bootstrap_token: str | None, ttl_seconds: int) -> None:
        self._launcher_token = bootstrap_token or secrets.token_urlsafe(48)
        self._launcher_consumed = False
        self._ttl_seconds = ttl_seconds
        self._sessions: dict[str, SessionPrincipal] = {}
        self._lock = threading.Lock()

    @property
    def launcher_token(self) -> str:
        """Return the operator-only token for launcher and test integration."""

        return self._launcher_token

    def exchange(self, presented_token: str) -> SessionPrincipal | None:
        with self._lock:
            if self._launcher_consumed or not hmac.compare_digest(
                presented_token,
                self._launcher_token,
            ):
                return None
            self._launcher_consumed = True
            principal = SessionPrincipal(
                token=secrets.token_urlsafe(48),
                csrf_token=secrets.token_urlsafe(32),
                expires_at=datetime.now(UTC) + timedelta(seconds=self._ttl_seconds),
            )
            self._sessions[principal.token] = principal
            return principal

    def authenticate(self, token: str | None) -> SessionPrincipal | None:
        if token is None:
            return None
        with self._lock:
            principal = self._sessions.get(token)
            if principal is None:
                return None
            if principal.expires_at <= datetime.now(UTC):
                self._sessions.pop(token, None)
                return None
            return principal

    def revoke(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)


class SlidingWindowRateLimiter:
    """Small in-process limiter appropriate for a single local instance."""

    def __init__(self, *, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        threshold = now - self.window_seconds
        with self._lock:
            hits = [hit for hit in self._hits.get(key, []) if hit >= threshold]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


class OriginValidationMiddleware(BaseHTTPMiddleware):
    """Reject cross-origin state changes before route processing."""

    def __init__(self, app: object, *, allowed_origins: tuple[str, ...]) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.allowed_origins = frozenset(allowed_origins)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin not in self.allowed_origins:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "error": {
                            "code": "origin_rejected",
                            "message": "The request origin is not allowed.",
                            "request_id": None,
                        }
                    },
                )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply browser hardening headers to API and same-origin frontend responses."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(self), microphone=(), geolocation=(), payment=(), usb=()"
        )
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'wasm-unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' blob: data:; "
            "connect-src 'self' ws://127.0.0.1:* ws://localhost:*; "
            "worker-src 'self' blob:; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        )
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject declared oversized HTTP bodies before multipart parsing."""

    def __init__(self, app: object, *, maximum_bytes: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.maximum_bytes = maximum_bytes

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "error": {
                            "code": "invalid_content_length",
                            "message": "Content-Length must be an integer.",
                            "request_id": None,
                        }
                    },
                )
            if declared < 0 or declared > self.maximum_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "error": {
                            "code": "request_too_large",
                            "message": "The request exceeds the configured size limit.",
                            "request_id": None,
                        }
                    },
                )
        return await call_next(request)


def _session_registry(request: Request) -> SessionRegistry:
    return request.app.state.services.sessions


def require_session(
    request: Request,
    cookie_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> SessionPrincipal:
    principal = _session_registry(request).authenticate(cookie_token)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "session_required", "message": "A valid local session is required."},
        )
    return principal


def require_csrf(
    principal: Annotated[SessionPrincipal, Depends(require_session)],
    csrf_token: Annotated[str | None, Header(alias=CSRF_HEADER)] = None,
) -> SessionPrincipal:
    if csrf_token is None or not hmac.compare_digest(csrf_token, principal.csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "csrf_rejected", "message": "The CSRF token is missing or invalid."},
        )
    return principal


def authenticate_websocket(websocket: WebSocket, settings: Settings) -> SessionPrincipal | None:
    origin = websocket.headers.get("origin")
    if origin not in settings.allowed_origins:
        return None
    token = websocket.cookies.get(SESSION_COOKIE)
    return websocket.app.state.services.sessions.authenticate(token)
