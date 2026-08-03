# WorldState: Persistent Spatial Memory on Consumer Hardware

## Engineering report

WorldState is a local-first system that converts ordinary monocular RGB video
into a persistent, queryable history of a physical workspace. Rather than
treating every camera frame as an independent prediction, it maintains
versioned entities, observations, evidence, spatial relationships, uncertainty,
and change events. The interface exposes that memory through live overlays,
Ghost Mode, a Time Scrubber, Object Memory, Last-Seen Search, a scene graph, and
uncertainty-guided scanning.

This document reports implemented capability and engineering measurements. It
does not claim research accuracy on real-world change detection or tracking;
those claims require the preregistered private Desk Change Set described in
[`docs/RESEARCH.md`](../docs/RESEARCH.md).

## System

The learned live pipeline is an adaptive cascade:

1. Grounding DINO Tiny performs scheduled open-vocabulary discovery in a
   reusable background inference executor.
2. SAM 2.1 Hiera Tiny produces masks on discovery frames.
3. Forward/backward Lucas-Kanade flow, RANSAC motion estimation, and a bounded
   template fallback propagate object state on the frame-critical path.
4. Depth Anything V2 Small estimates relative depth only when required.
5. DINOv2 ViT-S/14 supplies appearance features for identity association.
6. A gated Hungarian matcher combines label compatibility, overlap, motion,
   appearance, and three-dimensional proximity.
7. The temporal engine converts associated observations into append-only entity
   states, relationships, evidence, and explicit change events.

The offline scan path uses the Apache-licensed MapAnything checkpoint, then
Open3D cleanup and semantic lifting. It automatically degrades to
Depth Anything plus Open3D registration if the primary reconstruction exceeds
the GPU budget. Output without an external scale reference is labeled
approximate.

FastAPI coordinates the system but never runs learned inference in its event
loop. A supervised subprocess owns the GPU models, shared-memory frame
transport, bounded queues, warm-up, session resets, cancellation, and crash
recovery. The browser submits at most one frame at a time and waits for an
acknowledgement, preventing unbounded backlog.

The browser renders webcam pixels independently at display cadence and predicts
overlays between acknowledged results. Every live result updates the in-memory
world, while a bounded write-behind task checkpoints append-only temporal
history at a target cadence of 750 ms. Separate live-state and persistence locks
keep SQLite and artifact latency off the frame-acknowledgement path while
preserving last-seen and replay semantics.

## Persistence and security

SQLite stores relational state and runs in WAL mode inside the repository-local
`.worldstate/` data directory. Masks, depth maps, point clouds, meshes, and
model weights live beside it in SHA-256-addressed or checksum-pinned storage.
Entity history is interval-based and append-only, so current snapshots can be
rebuilt from observations and events.

The production service binds only to loopback. A launcher-generated one-time
fragment secret is exchanged for an HttpOnly SameSite cookie and then removed
from browser history. HTTP mutations use an in-memory CSRF token. HTTP and
WebSocket origins, hosts, schemas, sizes, rates, queues, media, storage, and
decoder work are bounded. Model files are allowlisted and checksum verified;
runtime inference never downloads weights implicitly.

## Measurement environment

- Windows 11 build 26200 with Ubuntu 24.04.4 under WSL2
- NVIDIA GeForce RTX 4060 Laptop GPU, 8,188 MiB
- NVIDIA driver 592.82
- Python 3.12.13
- PyTorch 2.11.0+cu128 and CUDA 12.8
- Node.js 24.12.0 and pnpm 10.33.0
- Six locally pinned model assets; lock SHA-256
  `0dd27568503a0e291bffd203f64d6665bd6ef3ec881382796e0ff842ccb589e3`

All live measurements use 640×360 inputs and acknowledgement-paced submission.
The exact current results and reproduction commands are maintained in
[`docs/MEASURED_STATUS.md`](../docs/MEASURED_STATUS.md). Raw benchmark reports
remain outside Git under `.worldstate/benchmarks`. The current repo-local live
report is `dynamic-e2e-soak-final-write-behind-30m.json`; its SHA-256 is
`2b3fe309c3075ffd183ab17e54a4d535480f5ce5aff06fc6ffbcd316246b3282`.

## Results

| Experiment | Observed result |
| --- | --- |
| Dynamic learned provider, 180 moving synthetic frames | 60.785 FPS; 16.45 ms mean; 33.31 ms p95; 2,406 MiB peak allocated VRAM |
| MapAnything, two synthetic 224×224 views | completed; 4,822 MiB peak allocated VRAM |
| Same-origin production workflow | secure bootstrap, local gesture asset, learned live sessions, scan, exports, worker suspend/restore, and cleanup passed |
| Initial 30-minute end-to-end soak | memory stable; 7.760 updates/s and 173.54 ms p95 missed the performance gates |
| Historical pre-flow 30-minute soak | 8.666 updates/s; 146.61 ms p95; stable memory; retained only as regression history |
| Current repo-local low-latency soak, 30 minutes | 55,689 learned frames; 30.930 updates/s; 24.45 ms median; 33.69 ms p95; 19.43 ms provider p95; 100% synthetic identity coverage; 0.277 px p95 center error; flat 2,588 MiB worker-reserved VRAM; all encoded gates passed |

The provider-only measurement is deliberately separated from end-to-end
latency. The latter includes JPEG decode, scheduling, learned inference,
association, persistence, protocol serialization, and the WebSocket round trip.

## Failure analysis and optimization

The first sustained runs exposed two independent systems bottlenecks. First,
synchronous mask refresh made previously discovered boxes appear frozen and
limited the live path to single-digit update rates. The current path moves
semantic discovery off the critical path and propagates state with optical
flow, RANSAC, and template fallback. Second, placing a SQLite transaction on
every display frame made storage latency visible to the camera view. Every
frame now updates the live belief state, while append-only durable history is
checkpointed every 750 ms.

An initial asynchronous implementation created a fresh inference thread for
every discovery and showed upward worker RSS. Replacing it with one reusable
executor made the worker slope flat. A later sustained run exposed a separate
long-tail failure: a repository-local durable checkpoint could block one live
acknowledgement for more than 30 seconds. WorldState now isolates its live cache
from a single bounded write-behind checkpoint task. The qualifying 30-minute
run completed with an API RSS slope of +0.346 MiB/minute, worker RSS slope of
+0.406 MiB/minute, and worker-reserved VRAM fixed at 2,588 MiB.

## Verification

The CPU suite contains 110 Python tests and reaches 88.61% total coverage. The
frontend contains 123 tests and reaches 89.03% statement coverage. Ruff,
Pyright, strict TypeScript, migrations, generated contracts, the production
build, Python and JavaScript vulnerability audits, and the default dependency
license policy pass.

Provider contract tests cover fake, replay, classical, and learned paths.
Hardware smoke tests cover persistent-worker reset, model checksums,
MapAnything inference, same-origin live capture, scanning, cancellation,
exports, and cleanup.

## Limitations and claim boundary

- Synthetic shapes demonstrate runtime behavior, not object-recognition
  accuracy.
- No change-event F1, IDF1, last-seen error, calibration error, or statistical
  comparison is claimed before the Desk Change Set is captured and frozen.
- Relative-depth and uncalibrated reconstruction outputs are not metric-scale
  measurements.
- HoloConsole recognition is geometry-tuned and unit tested, but its accidental
  activation rate still requires a real-hand user trial.
- Public demonstrations should use recorded or replay sessions; the local GPU
  backend is not designed for internet exposure.

The candidate research contribution is the combination of persistent change
memory, explicit belief state, adaptive inference, and active human guidance
under consumer-hardware constraints. Existing open-vocabulary 3D lifting and
scene-graph work is treated as prior art rather than claimed as novel.
