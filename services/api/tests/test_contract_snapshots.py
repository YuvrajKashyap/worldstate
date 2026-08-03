from __future__ import annotations

import json
from pathlib import Path

from worldstate_api.main import create_app
from worldstate_api.settings import Settings

ROOT = Path(__file__).resolve().parents[3]


def test_openapi_snapshot_matches_application(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            environment="test",
            data_root=tmp_path,
            persistence_enabled=False,
        )
    )
    try:
        expected = json.loads(
            (ROOT / "packages/contracts/openapi.json").read_text(encoding="utf-8")
        )
        assert app.openapi() == expected
    finally:
        app.state.services.close()


def test_protocol_schema_and_replay_fixture_are_versioned() -> None:
    protocol = json.loads(
        (ROOT / "packages/contracts/protocol-v1.schema.json").read_text(encoding="utf-8")
    )
    replay = json.loads(
        (ROOT / "packages/contracts/fixtures/desk-change-v1.json").read_text(encoding="utf-8")
    )

    assert protocol["title"] == "WorldState WebSocket Protocol v1"
    assert {
        "clientMessage",
        "serverMessage",
        "binaryFrameEnvelope",
    } <= protocol["$defs"].keys()
    assert replay["schema_version"] == 1
    assert replay["protocol_version"] == "v1"
    assert replay["expected_flow"][0] == "client.hello"
    assert replay["scripted_changes"][-1]["kind"] == "rediscovered"
