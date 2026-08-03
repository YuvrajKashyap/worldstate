"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from worldstate_api import __version__
from worldstate_api.api import api_router, public_router
from worldstate_api.live import live_router
from worldstate_api.security import (
    OriginValidationMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from worldstate_api.services import AppServices
from worldstate_api.settings import Settings
from worldstate_core.ids import uuid7

LOGGER = logging.getLogger("worldstate.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime = settings or Settings()
    services = AppServices(runtime)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        try:
            if runtime.provider_mode == "models":
                await asyncio.to_thread(services.providers.warmup)
            yield
        finally:
            services.close()

    app = FastAPI(
        title="WorldState API",
        summary="Local-first spatial memory and temporal scene understanding.",
        version=__version__,
        docs_url="/docs" if runtime.environment == "development" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if runtime.environment == "development" else None,
        lifespan=lifespan,
    )
    app.state.settings = runtime
    app.state.services = services

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-WorldState-CSRF",
            "X-Request-ID",
        ],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(
        OriginValidationMiddleware,
        allowed_origins=runtime.allowed_origins,
    )
    app.add_middleware(
        RequestSizeLimitMiddleware,
        maximum_bytes=runtime.max_upload_bytes + 1_048_576,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(runtime.allowed_hosts),
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = uuid7()
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        detail = error.detail
        if isinstance(detail, dict):
            detail_values = cast(dict[str, object], detail)
            code = str(detail_values.get("code", "http_error"))
            message = str(detail_values.get("message", "The request could not be completed."))
        else:
            code = "http_error"
            message = str(detail)
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "The request does not match the documented schema.",
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        LOGGER.exception(
            "Unhandled request failure",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "error_type": type(error).__name__,
            },
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "The local service encountered an unexpected error.",
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    app.include_router(public_router)
    app.include_router(api_router)
    app.include_router(live_router)

    frontend_dist = runtime.frontend_dist.resolve()
    if runtime.is_production and frontend_dist.is_dir():
        app.frontend("/", directory=str(frontend_dist))

    return app


app = create_app()
