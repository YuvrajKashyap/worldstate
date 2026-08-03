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

The default provider is deterministic replay. Set
`WORLDSTATE_PROVIDER_MODE=classical` for real weight-free OpenCV foreground
perception. Learned mode belongs in WSL after explicit setup and model
verification.

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

Run `scripts/setup-wsl.ps1`, then `scripts/models.ps1 -Defaults`. Add
`-IncludeReconstruction` only after checking storage because MapAnything is
substantially larger. Model access, CUDA builds, and checkpoint downloads stay
outside bootstrap and CI. Every provider documents:

- Upstream repository and revision.
- Checkpoint and license.
- Install command.
- Hardware requirements.
- Memory and timing profile.
- Failure behavior and fallback.

## Contracts and migrations

```powershell
pnpm contracts:generate
uv run python scripts/verify-migrations.py
```

Generated artifacts live in `packages/contracts` and must be committed with
backend contract changes. `scripts/verify.ps1` rejects drift. Alembic is
configured under `services/api/alembic`.
