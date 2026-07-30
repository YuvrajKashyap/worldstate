"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from worldstate_api import __version__
from worldstate_api.schemas import HealthResponse, SystemResponse
from worldstate_api.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    runtime = settings or Settings()
    app = FastAPI(
        title="WorldState API",
        version=__version__,
        docs_url="/docs" if runtime.environment == "development" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if runtime.environment == "development" else None,
    )
    app.state.settings = runtime
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="worldstate-api", version=__version__)

    @app.get("/api/v1/system", response_model=SystemResponse, tags=["system"])
    async def system() -> SystemResponse:
        return SystemResponse(
            environment=runtime.environment,
            persistence_enabled=runtime.persistence_enabled,
            protocol_version="v1",
            product_phase="foundation",
        )

    return app


app = create_app()
