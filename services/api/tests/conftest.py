from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from worldstate_api.main import create_app
from worldstate_api.settings import Settings

ORIGIN = "http://127.0.0.1:5173"
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class AuthenticatedClient(NamedTuple):
    client: TestClient
    app: FastAPI
    mutation_headers: dict[str, str]


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[AuthenticatedClient]:
    settings = Settings(
        environment="test",
        data_root=tmp_path,
        persistence_enabled=False,
        model_manifest_path=PROJECT_ROOT / "configs" / "models.yaml",
        model_lock_path_override=tmp_path / "models.lock.json",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        token = app.state.services.sessions.launcher_token
        response = client.post(
            "/api/v1/bootstrap",
            headers={"Origin": ORIGIN},
            json={"token": token},
        )
        assert response.status_code == 200
        csrf_token = response.json()["csrf_token"]
        yield AuthenticatedClient(
            client,
            app,
            {"Origin": ORIGIN, "X-WorldState-CSRF": csrf_token},
        )
