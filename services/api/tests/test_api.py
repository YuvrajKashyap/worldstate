from fastapi.testclient import TestClient

from worldstate_api.main import create_app
from worldstate_api.settings import Settings


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
    assert response.json() == {
        "environment": "test",
        "persistence_enabled": False,
        "protocol_version": "v1",
        "product_phase": "foundation",
    }


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
