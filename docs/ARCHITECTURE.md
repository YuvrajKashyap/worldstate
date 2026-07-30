# Architecture

WorldState is a local-first modular monolith with one browser client, one
application coordinator, one bounded GPU scheduler, and a framework-independent
world-model package.

## Dependency direction

```text
web client ---> API coordinator ---> worldstate-core
                         |                 ^
                         v                 |
                  provider adapters -------+
                         |
                         v
                 local artifact store
```

Rules:

- `worldstate-core` does not import FastAPI, React, SQLAlchemy, or model-specific
  packages.
- Model integrations implement typed ports owned by the core package.
- API schemas do not expose model-internal tensors or absolute local paths.
- The browser receives derived scene state and bounded artifacts, not arbitrary
  backend objects.

## Runtime surfaces

### Browser

- Captures webcam frames.
- Enforces one frame in flight.
- Renders the memory volume and historical state.
- Runs hand landmarks and gesture-state logic.
- Exposes mouse, keyboard, and touch parity.

### API coordinator

- Validates origins and requests.
- Owns session and job lifecycles.
- Applies backpressure.
- Dispatches bounded GPU work.
- Translates domain state to versioned transport schemas.

### World model

- Separates observation from belief.
- Maintains static, persistent, transient, and historical layers.
- Associates observations with entity hypotheses.
- Applies confidence decay and presence-state transitions.
- Produces events, relationships, uncertainty, and evidence references.

### Providers

Providers are replaceable adapters:

- Geometry provider.
- Perception provider.
- Appearance provider.
- Artifact store.
- Persistence store.
- Clock and ID providers for deterministic tests.

### Persistence

Relational state belongs in SQLite. Large arrays and geometry belong in a
content-addressed artifact store. Experiment tables belong in Parquet. Raw
continuous webcam video is not persisted by default.

## Workload classes

### Live

- Low latency.
- One frame in flight.
- Dropped intervals are measured.
- Uses lightweight models and adaptive refresh.

### Scan

- Higher quality, bounded batch job.
- Keyframes are selected before expensive inference.
- Models may load sequentially to respect VRAM limits.
- Cancellation is explicit and recoverable.

### Research

- Fixed dataset and configuration.
- Deterministic where supported.
- Full provenance and raw metrics.
- Never changes the interactive product state.

## Static and dynamic separation

The base map contains surfaces expected to remain fixed. Movable objects retain
their own geometry and poses. Hands and people are transient masks and are
excluded from static fusion. This prevents a moving hand or relocated mug from
becoming permanent room geometry.

## Transport

REST handles scenes, scans, objects, events, exports, and system state. A binary
WebSocket handles live frames and frame results. Every packet has a protocol
version, sequence number, capture timestamp, and presentation timestamp.

## Performance policy

- No unbounded queue.
- No simultaneous heavyweight model residency before profiling.
- No native extension before a correct baseline and profiler evidence.
- No published number without input, hardware, configuration, and commit
  provenance.

## Architecture decisions

See [docs/adr](adr/) for durable decisions and their tradeoffs.
