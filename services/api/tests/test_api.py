from pathlib import Path

from fastapi.testclient import TestClient

from worldstate_api.main import create_app
from worldstate_api.settings import Settings


def test_default_storage_is_repository_local() -> None:
    settings = Settings(environment="test", persistence_enabled=True)

    assert settings.data_root == Path(".worldstate")
    assert ".worldstate/db/worldstate.sqlite3" in settings.database_url.replace("\\", "/")


def test_health_response_is_versioned() -> None:
    client = TestClient(create_app(Settings(environment="test")))

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "worldstate-api",
        "version": "0.1.0",
    }


def test_system_response_does_not_expose_local_paths() -> None:
    client = TestClient(create_app(Settings(environment="test", persistence_enabled=False)))

    response = client.get("/api/v1/system")

    assert response.status_code == 200
    payload = response.json()
    assert payload["environment"] == "test"
    assert payload["persistence_enabled"] is False
    assert payload["protocol_version"] == "v1"
    assert payload["product_phase"] == "operational"
    assert payload["provider_mode"] == "replay"
    assert payload["capabilities"]["live_replay"] == "ready"
    assert "limits" in payload
    assert "data_root" not in payload
    assert "database_url" not in payload


def test_settings_reject_wildcard_origin() -> None:
    settings = Settings(allowed_origins_csv="*")

    try:
        _ = settings.allowed_origins
    except ValueError as error:
        assert str(error) == "wildcard origins are not permitted"
    else:
        raise AssertionError("wildcard origin was accepted")


def test_settings_reject_empty_origin_list() -> None:
    settings = Settings(allowed_origins_csv=" , ")

    try:
        _ = settings.allowed_origins
    except ValueError as error:
        assert str(error) == "at least one allowed origin is required"
    else:
        raise AssertionError("empty origin list was accepted")


def test_production_serves_static_frontend_and_disables_api_docs(tmp_path: Path) -> None:
    frontend = tmp_path / "dist"
    frontend.mkdir()
    (frontend / "index.html").write_text("<!doctype html><title>WorldState</title>")
    app = create_app(
        Settings(
            environment="production",
            data_root=tmp_path / "data",
            frontend_dist=frontend,
            allowed_origins_csv="http://127.0.0.1:8000",
        )
    )

    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "WorldState" in response.text
        assert "'wasm-unsafe-eval'" in response.headers["content-security-policy"]
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
