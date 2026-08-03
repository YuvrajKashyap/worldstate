#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:?repository path required}"
cd "$ROOT"

export UV_PROJECT_ENVIRONMENT=/opt/worldstate/venv
export UV_PYTHON_INSTALL_DIR=/opt/worldstate/python
export UV_CACHE_DIR=/var/cache/worldstate-uv
export WORLDSTATE_ENVIRONMENT=production
export WORLDSTATE_HOST=127.0.0.1
export WORLDSTATE_PORT=8000
export WORLDSTATE_ALLOWED_ORIGINS=http://127.0.0.1:8000
export WORLDSTATE_ALLOWED_HOSTS=127.0.0.1,localhost
export WORLDSTATE_PERSISTENCE_ENABLED=true
export WORLDSTATE_DATA_ROOT="$ROOT/.worldstate"
export WORLDSTATE_DATABASE_URL="sqlite:///$ROOT/.worldstate/db/worldstate.sqlite3"
export WORLDSTATE_PROVIDER_MODE="${WORLDSTATE_PROVIDER_MODE:-models}"
export WORLDSTATE_BOOTSTRAP_TOKEN
WORLDSTATE_BOOTSTRAP_TOKEN="${WORLDSTATE_BOOTSTRAP_TOKEN:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')}"

url="http://127.0.0.1:8000/#bootstrap=${WORLDSTATE_BOOTSTRAP_TOKEN}"
if [[ "${WORLDSTATE_OPEN_BROWSER:-1}" == "1" ]]; then
  (
    for _ in $(seq 1 1200); do
      if curl --fail --silent http://127.0.0.1:8000/healthz >/dev/null; then
        powershell.exe -NoProfile -Command "Start-Process '$url'"
        exit 0
      fi
      sleep 0.1
    done
    echo "WorldState did not become healthy in time." >&2
  ) &
fi

exec uv run worldstate serve
