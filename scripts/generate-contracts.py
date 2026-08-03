"""Generate immutable frontend-facing WorldState protocol artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from pydantic import Field, TypeAdapter

from worldstate_api.contracts import (
    ClientHello,
    CommandResult,
    CommandSubmit,
    EventBatch,
    FlowSlowDown,
    FrameEnvelopeMetadata,
    FrameResult,
    ServerReady,
    WebSocketError,
    WorldPatch,
)
from worldstate_api.main import create_app
from worldstate_api.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "packages" / "contracts"

ClientMessage = Annotated[ClientHello | CommandSubmit, Field(discriminator="type")]
ServerMessage = Annotated[
    ServerReady
    | FrameResult
    | WorldPatch
    | EventBatch
    | CommandResult
    | FlowSlowDown
    | WebSocketError,
    Field(discriminator="type"),
]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    settings = Settings(
        environment="test",
        persistence_enabled=False,
        data_root=Path(".worldstate"),
    )
    app = create_app(settings)
    try:
        write_json(CONTRACTS / "openapi.json", app.openapi())
        write_json(
            CONTRACTS / "protocol-v1.schema.json",
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "https://worldstate.local/contracts/protocol-v1.schema.json",
                "title": "WorldState WebSocket Protocol v1",
                "type": "object",
                "$defs": {
                    "clientMessage": TypeAdapter(ClientMessage).json_schema(),
                    "serverMessage": TypeAdapter(ServerMessage).json_schema(),
                    "binaryFrameEnvelope": FrameEnvelopeMetadata.model_json_schema(),
                },
                "properties": {
                    "client": {"$ref": "#/$defs/clientMessage"},
                    "server": {"$ref": "#/$defs/serverMessage"},
                    "binaryFrameEnvelope": {"$ref": "#/$defs/binaryFrameEnvelope"},
                },
            },
        )
        write_json(
            CONTRACTS / "fixtures" / "desk-change-v1.json",
            {
                "schema_version": 1,
                "protocol_version": "v1",
                "replay": {
                    "id": "desk-change-v1",
                    "name": "Desk Change",
                    "duration_seconds": 24.0,
                    "frame_count": 240,
                },
                "scene": {
                    "id": "018f0000-0000-7000-8000-000000000001",
                    "name": "Replay Desk",
                    "object_prompts": ["cup", "book", "phone"],
                },
                "capture_session": {
                    "id": "018f0000-0000-7000-8000-000000000002",
                    "mode": "replay",
                },
                "expected_flow": [
                    "client.hello",
                    "server.ready",
                    "frame.result",
                    "command.submit",
                    "command.result",
                ],
                "scripted_changes": [
                    {"at_seconds": 0.0, "kind": "added", "label": "cup"},
                    {"at_seconds": 6.0, "kind": "moved", "label": "cup"},
                    {"at_seconds": 12.0, "kind": "missing", "label": "book"},
                    {"at_seconds": 18.0, "kind": "rediscovered", "label": "book"},
                ],
            },
        )
    finally:
        app.state.services.close()


if __name__ == "__main__":
    main()
