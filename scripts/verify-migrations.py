"""Exercise the complete Alembic upgrade/downgrade path on an isolated database."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "services" / "api"


def alembic(*arguments: str, environment: dict[str, str]) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=API_ROOT,
        env=environment,
        check=True,
        timeout=60,
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="worldstate-migration-") as temporary:
        root = Path(temporary)
        database_path = root / "worldstate.sqlite3"
        environment = os.environ.copy()
        environment.update(
            {
                "WORLDSTATE_ENVIRONMENT": "test",
                "WORLDSTATE_PERSISTENCE_ENABLED": "true",
                "WORLDSTATE_DATA_ROOT": str(root),
                "WORLDSTATE_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            }
        )
        alembic("upgrade", "head", environment=environment)
        alembic("check", environment=environment)

        engine = create_engine(f"sqlite:///{database_path.as_posix()}")
        try:
            tables = set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
        required = {
            "scenes",
            "capture_sessions",
            "frames",
            "observations",
            "entities",
            "entity_states",
            "evidence",
            "world_events",
            "relationships",
            "jobs",
            "model_runs",
            "artifacts",
            "exports",
        }
        missing = required - tables
        if missing:
            raise RuntimeError(f"migration did not create required tables: {sorted(missing)}")

        alembic("downgrade", "base", environment=environment)
        alembic("upgrade", "head", environment=environment)


if __name__ == "__main__":
    main()
