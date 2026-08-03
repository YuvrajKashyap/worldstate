# Testing

## Model-free checks

The standard verification script runs:

- Ruff format and lint.
- Pyright strict type checking.
- Pytest with branch coverage.
- Alembic upgrade/check/downgrade/upgrade.
- Generated OpenAPI, JSON Schema, and TypeScript contract drift checks.
- ESLint.
- TypeScript strict build.
- Vitest with coverage.
- Vite production build.
- Python and JavaScript dependency vulnerability audits.
- Default Python dependency license policy.

## Test layers

### Unit

- Domain invariants.
- Presence transitions.
- Confidence decay.
- Geometry transforms and metrics.
- Gesture-state transitions.

### Property

- Confidence remains bounded.
- Transform round trips remain within tolerance.
- Event history is append-only.
- Deletion removes every referenced artifact.

### Contract

- Provider adapters return normalized results.
- Public API schemas remain versioned.
- No absolute local path reaches a response.

### Integration

- Camera lifecycle.
- Bounded live queue.
- Job cancellation.
- Persistence and complete deletion.
- Scan artifact handoff.

### GPU

- Dynamic learned-provider tracking, latency, identity, and drift profile.
- Persistent subprocess warm-up, reset, cancellation, and teardown.
- Per-worker PyTorch allocated/reserved VRAM and whole-GPU capacity sampling.
- MapAnything multi-view inference and bounded VRAM.
- Same-origin live, scan, fallback, export, and cleanup workflow.
- Thirty-minute acknowledgement-paced live stability soak.

GPU tests are local or explicitly provisioned. They do not run in ordinary CI.
Commands and the current measured results are documented in
[MEASURED_STATUS.md](MEASURED_STATUS.md); raw local reports live outside Git
under `.worldstate/benchmarks`.
