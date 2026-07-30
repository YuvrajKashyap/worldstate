# Development

## Bootstrap

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

Bootstrap installs a uv-managed Python 3.12 runtime when needed, synchronizes
model-free Python dependencies, and installs frontend dependencies. It does not
download models.

Install the repository hooks once per clone:

```powershell
uv run pre-commit install
```

## API

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev-api.ps1
```

Health endpoint: `http://127.0.0.1:8000/healthz`

## Web

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev-web.ps1
```

Interface: `http://127.0.0.1:5173`

## Verification

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## Heavy providers

Model access, CUDA builds, and checkpoint downloads are separate feasibility
steps. Do not add them to bootstrap or CI. Every provider must document:

- Upstream repository and revision.
- Checkpoint and license.
- Install command.
- Hardware requirements.
- Memory and timing profile.
- Failure behavior and fallback.
