#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:?repository path required}"
DATA_ROOT="$ROOT/.worldstate"
RUNTIME_USER="worldstate"
RUNTIME_HOME="/home/$RUNTIME_USER"
RUNTIME_ROOT="/opt/worldstate"
UV_CACHE_ROOT="/var/cache/worldstate-uv"

if [[ ! -f /etc/os-release ]] || ! grep -q 'Ubuntu 24.04' /etc/os-release; then
  echo "WorldState requires Ubuntu 24.04 under WSL2." >&2
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "The WSL bootstrap must run as root." >&2
  exit 1
fi

apt-get update
apt-get install -y --no-install-recommends \
  build-essential ca-certificates curl ffmpeg git libgl1 libglib2.0-0 pkg-config

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="/root/.local/bin:$PATH"
fi

install -m 0755 "$(command -v uv)" /usr/local/bin/uv
if command -v uvx >/dev/null 2>&1; then
  install -m 0755 "$(command -v uvx)" /usr/local/bin/uvx
fi

if ! id "$RUNTIME_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$RUNTIME_USER"
fi

install -d -o "$RUNTIME_USER" -g "$RUNTIME_USER" \
  "$RUNTIME_HOME" \
  "$RUNTIME_ROOT" \
  "$UV_CACHE_ROOT"
mkdir -p "$DATA_ROOT"/{artifacts,db,exports,models,uploads,work}
chown -R "$RUNTIME_USER:$RUNTIME_USER" "$DATA_ROOT" "$RUNTIME_ROOT" "$UV_CACHE_ROOT"

export UV_PROJECT_ENVIRONMENT="$RUNTIME_ROOT/venv"
export UV_PYTHON_INSTALL_DIR="$RUNTIME_ROOT/python"
export UV_CACHE_DIR="$UV_CACHE_ROOT"

cd "$ROOT"
uv python install 3.12
SAM2_BUILD_CUDA=0 uv sync \
  --all-packages \
  --group dev \
  --extra vision \
  --extra geometry \
  --extra evaluation \
  --locked
chown -R "$RUNTIME_USER:$RUNTIME_USER" "$RUNTIME_ROOT" "$UV_CACHE_ROOT"

echo "Checking the Windows GPU bridge..."
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
else
  echo "nvidia-smi is unavailable inside WSL. Install/update the NVIDIA Windows driver." >&2
fi

runuser -u "$RUNTIME_USER" -- env \
  UV_PROJECT_ENVIRONMENT="$RUNTIME_ROOT/venv" \
  UV_PYTHON_INSTALL_DIR="$RUNTIME_ROOT/python" \
  UV_CACHE_DIR="$UV_CACHE_ROOT" \
  uv run python -c \
  "import torch; assert torch.cuda.is_available(); print(torch.__version__, torch.version.cuda, torch.cuda.get_device_name(0))"

echo "WSL backend is ready under the unprivileged '$RUNTIME_USER' account. Model downloads remain explicit."
