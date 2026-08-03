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

Learned live inference runs behind a supervised spawned process. Frames cross
that boundary through bounded shared memory rather than queue serialization.
The worker is configured for offline Hugging Face/Transformers operation,
returns only normalized dataclasses, and is stopped on timeout or protocol
desynchronization. Production warms this worker before reporting healthy and
retains it across capture sessions while resetting session-local tracking
state. Exclusive reconstruction suspends it to release VRAM and restores it
before the scheduler accepts another live session. Replay and OpenCV remain
in-process because they are weight-free and used by CPU CI.

The learned provider keeps heavy open-vocabulary discovery off the frame
critical path. A single reusable background executor runs Grounding DINO, SAM,
DINOv2, and depth at scheduled or uncertainty-triggered intervals. Between
discoveries, forward/backward Lucas-Kanade flow, RANSAC motion estimation, and
a bounded template fallback propagate object state. The reusable executor is a
stability requirement: creating a new PyTorch inference thread per discovery
caused thread-local CPU and CUDA allocator growth during sustained capture.

### Persistence

Relational state belongs in SQLite. The supported local layout keeps the
database, large arrays, model weights, uploads, and geometry together under
the repository-local `.worldstate/` directory. A single bounded write-behind
task and separate live-state/persistence locks decouple rendering from 750 ms
durable checkpoints, so mounted-filesystem WAL latency cannot block a display
frame. Experiment tables belong in Parquet. Raw continuous webcam video is not
persisted by default.

Artifact ownership is an explicit relational edge to a scene, session, or job.
Scene deletion decrements those edges before reference-aware garbage
collection, so privacy lifecycle is not inferred from filenames.

## Workload classes

### Live

- Low latency.
- One frame in flight.
- Dropped intervals are measured.
- Webcam pixels render directly at display cadence; overlays predict between
  acknowledged results.
- Uses optical-flow tracking with asynchronous semantic correction.
- Checkpoints durable temporal memory every 750 ms while every frame remains
  available to the live view.

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
