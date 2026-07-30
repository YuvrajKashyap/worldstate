# Testing

## Model-free checks

The standard verification script runs:

- Ruff format and lint.
- Pyright strict type checking.
- Pytest with branch coverage.
- ESLint.
- TypeScript strict build.
- Vitest with coverage.
- Vite production build.

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

- Fixed-provider smoke tests.
- Memory and latency profile.
- Real multi-view fixture.
- Mixed-precision comparison.

GPU tests are local or explicitly provisioned. They do not run in ordinary CI.
