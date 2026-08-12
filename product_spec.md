# WorldState Product Specification

Status: Approved foundation specification
Version: 0.1
Owner: Yuvraj Kashyap
Repository: `YuvrajKashyap/worldstate`
Tagline: A persistent visual memory for physical spaces.

## 1. Executive summary

WorldState is a local-first spatial-computing system that turns ordinary RGB
camera input into a persistent, queryable memory of a physical space. It uses a
laptop webcam for continuous desk-scale observation and optional phone or
uploaded video for multi-view reconstruction. It separates static geometry,
movable objects, and transient agents; records how objects change over time;
exposes evidence and uncertainty; and renders the result as an interactive 3D
world.

WorldState is both:

1. A polished product demonstration with a memorable spatial interface.
2. A reproducible computer-vision research system with explicit hypotheses,
   baselines, metrics, ablations, and hardware measurements.

The project must not become a wrapper around pretrained models. Its central
engineering contribution is the world model that turns frame-level predictions
into persistent state: object identity, evidence, uncertainty, relationships,
events, and history.

## 2. Product thesis

Most camera systems answer a question about the current frame. WorldState
answers questions about a place over time.

The core product promise is:

> Show WorldState a workspace and it will remember what exists, where it was,
> what changed, how certain it is, and which observations support that memory.

## 3. Target audience

### Primary user

A technically curious single operator using a consumer Windows laptop with an
NVIDIA GPU and an ordinary webcam.

### Secondary audiences

- Computer-vision and spatial-computing engineers evaluating the implementation.
- Technical reviewers and engineering teams assessing product judgment, ML rigor, and systems
  engineering.
- Researchers reproducing the experimental comparisons.
- Developers extending the model adapters or world-state engine.

## 4. Product principles

1. **Memory, not detection.** Frame-level model output is an observation, never
   the source of truth.
2. **Evidence before certainty.** Every important claim is traceable to frames,
   masks, geometry, model versions, and confidence.
3. **Uncertainty is visible.** Unknown, predicted, stale, and observed states
   must look different.
4. **Local by default.** Camera data and scene memory stay on the user's machine
   unless the user explicitly exports them.
5. **Bounded work.** Live capture uses backpressure and never accumulates an
   unbounded inference queue.
6. **Models are replaceable.** Geometry, segmentation, embeddings, and tracking
   sit behind typed adapters.
7. **Claims are measured.** Accuracy, latency, and robustness statements require
   dated, reproducible evidence.
8. **One coherent flagship.** HoloConsole, research tooling, and the spatial
   viewer are parts of WorldState, not disconnected side projects.
9. **People are transient.** WorldState does not create persistent biometric
   identities or infer sensitive personal traits.
10. **Polish serves comprehension.** Visual effects communicate state,
    confidence, history, or control; they are not decorative noise.

## 5. Non-goals

The initial product will not:

- Identify people or build persistent person profiles.
- Infer race, ethnicity, health, religion, disability, political affiliation,
  sexual orientation, or other sensitive personal traits from appearance.
- Provide security, surveillance, or access-control decisions.
- Promise centimeter-perfect geometry from a fixed monocular webcam.
- Run every foundation model continuously or simultaneously.
- Train a large foundation model from scratch.
- Depend on cloud inference, a managed database, LiDAR, or a depth camera.
- Support multiple buildings, users, or concurrent GPU workloads in the MVP.
- Claim academic novelty merely for producing an open-vocabulary 3D scene graph.

## 6. Product modes

### 6.1 Live Desk Mode

The laptop webcam continuously observes one workspace.

Capabilities:

- Detect and segment ordinary objects.
- Maintain persistent object records.
- Estimate approximate depth and spatial relationships.
- Distinguish visibility, occlusion, prediction, absence, and rediscovery.
- Detect additions, removals, translations, and rotations.
- Update the scene graph and event timeline.
- Answer last-seen and change queries.
- Preserve bounded latency by dropping capture intervals when inference is busy.

### 6.2 Spatial Scan Mode

The user supplies a short moving-camera video from a webcam, phone, or file.

Capabilities:

- Reject blurred, redundant, or low-information frames.
- Select useful keyframes.
- Estimate camera intrinsics, camera trajectory, depth, and 3D points.
- Segment objects across views.
- Lift semantic observations into a shared coordinate system.
- Align a new scan to an existing scene.
- Update static geometry and persistent objects independently.
- Produce a portable reconstruction and scan-quality report.

### 6.3 HoloConsole

The webcam feed becomes the background for an interactive spatial console.
Hand landmarks are processed client-side for responsive control.

Required interactions:

- Point to raycast into the scene.
- Pinch to select.
- Pinch and drag to reposition the holographic world.
- Twist a wrist to rotate.
- Spread two hands to enlarge.
- Bring two hands together to shrink.
- Swipe horizontally to scrub time.
- Open a palm to expand object memory, relationships, and evidence.
- Frame an object with two hands to isolate it.
- Push to return from history to the live state.
- Perform a deliberate summon gesture to enter HoloConsole.

The interaction engine must include landmark smoothing, gesture hysteresis,
activation thresholds, cancellation behavior, two-hand state management,
confidence handling, and accidental-trigger suppression.

### 6.4 Evidence Mode

Every object and event can expose:

- Supporting keyframes.
- Source timestamps and camera poses.
- Segmentation masks and geometry.
- Current and historical confidence.
- Model and checkpoint provenance.
- Viewpoint agreement and conflicts.
- The rule that classified an event.
- Alternative hypotheses when confidence is insufficient.

### 6.5 Research Mode

Research Mode runs datasets and recorded sessions through fixed configurations,
records all parameters and provenance, computes metrics, produces comparison
tables, and regenerates paper figures.

## 7. Flagship demonstration

The north-star demonstration must fit within approximately 60 seconds:

1. WorldState opens on a webcam view of a desk.
2. Static surfaces and persistent objects appear in the spatial viewer.
3. The user moves headphones and removes a mug.
4. Change pulses mark both events.
5. Ghost Mode renders the previous positions.
6. The user summons HoloConsole with both hands.
7. Two-hand gestures rotate and enlarge the reconstructed workspace.
8. A horizontal swipe moves backward through time.
9. The user points at the missing mug.
10. Object Memory reports its last location and observation time.
11. Evidence Mode shows the supporting frames and confidence.
12. An uncertain region becomes fog and Active Scan Coach requests a useful
    additional viewpoint.

## 8. Signature product features

### 8.1 Ghost Mode

Previous object positions remain as translucent 3D outlines. Ghosts encode the
event type, timestamp, and confidence instead of acting as generic decoration.

### 8.2 Time Scrubber

The user drags through scene states. Geometry, objects, relationships, evidence,
and uncertainty update to the selected time without mutating the live state.

### 8.3 Change Pulses

New, moved, rediscovered, or removed objects emit restrained event pulses.
Pulse color and behavior encode the event type.

### 8.4 Object Memory

Selecting an object reveals:

- Current state.
- First and last observation.
- Movement and event history.
- Relationships.
- Supporting evidence.
- Confidence and uncertainty.
- Model provenance.

### 8.5 Uncertainty View

Low-confidence geometry appears as unstable particles or fog. Stale object
memory fades. Conflicting observations visibly disagree instead of being hidden.

### 8.6 Scene Graph

Objects and spatial relationships can be rendered as an animated graph over the
3D scene. Graph nodes remain linked to concrete entities and evidence.

### 8.7 Last-Seen Search

The user can locate when and where an object was last observed, with evidence
and a clear distinction between "last seen" and "currently present."

### 8.8 Active Scan Coach

WorldState estimates where additional evidence would be most valuable and gives
specific instructions:

- Move left or right to add parallax.
- Lower or raise the camera.
- Reveal an occluded surface.
- Hold still when motion blur is high.
- Revisit an uncertain object.
- Stop when marginal information gain is low.

### 8.9 X-ray Memory

Occluded or missing objects remain visible using an explicit visual grammar:

- Solid: currently observed.
- Wireframe: temporarily occluded.
- Amber pulse: predicted with meaningful uncertainty.
- Red ghost: missing from an expected location.
- Fading particles: stale, low-confidence memory.

## 9. World model

### 9.1 Layers

WorldState maintains four separate layers:

1. **Static world:** walls, desk, shelves, and fixed fixtures.
2. **Persistent objects:** movable ordinary objects such as mugs, notebooks,
   headphones, and keyboards.
3. **Transient agents:** hands and people observed for immediate interaction but
   never fused into static geometry or assigned persistent biometric identities.
4. **Historical memory:** observations, states, relationships, events, evidence,
   and confidence over time.

### 9.2 Presence lifecycle

Persistent objects use an explicit lifecycle:

```text
visible -> occluded -> predicted -> missing -> rediscovered -> archived
```

Rules:

- Confidence decays while evidence is absent.
- Occlusion does not immediately imply removal.
- Prediction is time-limited and labeled as prediction.
- Rediscovery requires semantic, geometric, appearance, and temporal support.
- A low-confidence match may remain unresolved instead of forcing an identity.

### 9.3 Domain entities

- `Scene`
- `ScanSession`
- `Camera`
- `Keyframe`
- `Observation`
- `StaticSurface`
- `Entity`
- `ObjectState`
- `Relationship`
- `Event`
- `Evidence`
- `UncertaintyEstimate`
- `ModelRun`
- `Artifact`

### 9.4 Persistent identity

Cross-frame and cross-session association combines:

- 2D overlap.
- 3D overlap and distance.
- Appearance embeddings.
- Semantic compatibility.
- Motion plausibility.
- Viewpoint consistency.
- Temporal gap.
- Object dimensions and shape.

No single model score is treated as a calibrated probability or permanent
identity decision.

## 10. Functional requirements

### Capture

- `CAP-001`: Capture webcam frames only after explicit permission.
- `CAP-002`: Stop every media track when capture ends or the page unmounts.
- `CAP-003`: Permit only one frame in flight per live client by default.
- `CAP-004`: Count skipped capture intervals rather than queueing them.
- `CAP-005`: Accept common uploaded video formats through a normalized ingest
  path.
- `CAP-006`: Preserve capture and presentation timestamps.

### Perception

- `PER-001`: Run perception through typed adapters.
- `PER-002`: Return masks, boxes, labels, scores, embeddings, and provenance
  without requiring every provider to implement every field.
- `PER-003`: Support a bounded-latency live provider and a high-quality scan
  provider.
- `PER-004`: Reject sensitive-trait prompt lists.
- `PER-005`: Mark raw model scores as uncalibrated unless a calibration
  experiment proves otherwise.

### Geometry

- `GEO-001`: Estimate camera parameters, depth, 3D points, confidence, and
  coordinate transforms through a replaceable provider.
- `GEO-002`: Keep static geometry independent from movable object geometry.
- `GEO-003`: Align later scans to the scene with measurable confidence.
- `GEO-004`: Preserve metric units when available and label approximate scale.
- `GEO-005`: Export PLY and GLB representations.

### Memory

- `MEM-001`: Store observations separately from inferred object state.
- `MEM-002`: Preserve object state history without overwriting past states.
- `MEM-003`: Apply explicit confidence decay.
- `MEM-004`: Support unresolved identity hypotheses.
- `MEM-005`: Retain evidence references for every important event.
- `MEM-006`: Delete a scene and all associated artifacts atomically.

### Events and relationships

- `EVT-001`: Detect added, moved, rotated, removed, occluded, and rediscovered
  events.
- `EVT-002`: Assign event confidence and evidence.
- `EVT-003`: Derive spatial relationships from geometry with tolerances.
- `EVT-004`: Never describe a predicted state as directly observed.

### Interface

- `UI-001`: Keep the 3D world as the primary visual surface.
- `UI-002`: Provide Ghost Mode, timeline, change pulses, uncertainty, scene
  graph, last-seen search, Object Memory, and Evidence Mode.
- `UI-003`: Remain keyboard operable when gesture controls are unavailable.
- `UI-004`: Respect reduced-motion preferences.
- `UI-005`: Keep critical status readable without depending on color alone.

### HoloConsole

- `HOL-001`: Process hand landmarks in the browser.
- `HOL-002`: Separate gesture recognition from interaction state.
- `HOL-003`: Require deliberate activation before continuous controls.
- `HOL-004`: Expose gesture confidence and an immediate cancel action.
- `HOL-005`: Prevent scene mutations while viewing historical state.

### Research

- `RES-001`: Version experiment configurations.
- `RES-002`: Record code commit, hardware, driver, CUDA, model, checkpoint,
  dataset, input hash, and random seeds.
- `RES-003`: Preserve runnable baselines.
- `RES-004`: Regenerate tables and figures from raw experiment artifacts.
- `RES-005`: Separate design targets from measured results.

## 11. Technical architecture

### Client

- React 19, TypeScript, and Vite.
- Three.js and React Three Fiber.
- Custom shader-based point, surfel, ghost, and uncertainty rendering.
- Zustand for UI and scene-view state.
- XState for HoloConsole interaction state.
- MediaPipe Hand Landmarker in a browser worker.
- Binary WebSockets for live frames and typed results.

### Application coordinator

- Python 3.12.
- FastAPI, Pydantic v2, and Uvicorn.
- REST for scenes, scans, events, objects, exports, and system status.
- WebSockets for live observations.
- One bounded GPU scheduler.
- Background scan and export jobs.

### Vision and geometry

- PyTorch with a pinned CUDA-compatible build after the feasibility spike.
- OpenCV, PyAV, FFmpeg, NumPy, and SciPy.
- MapAnything as the primary learned-geometry candidate.
- VGGT and PyCOLMAP/COLMAP as learned and classical comparison providers.
- Open3D for point clouds, registration, fusion, and evaluation.
- A bounded-latency live segmenter.
- SAM 3.1 as an experimental high-quality scan provider when memory permits.
- DINOv2 and/or SigLIP 2 embeddings behind an appearance provider.

### State and persistence

- A framework-independent `worldstate-core` Python package.
- SQLite, SQLAlchemy 2, and Alembic for relational state.
- Zarr for chunked arrays.
- Content-addressed local artifacts.
- Parquet for experiment results.
- PLY and GLB exports.

### Native optimization

- C++20 and CUDA C++ after a correct Python baseline exists.
- CMake and pybind11 or PyTorch C++ extensions.
- Candidate kernels: mask lifting, sparse voxel fusion, multiview overlap, and
  point association.
- Nsight Systems and Nsight Compute for profiling.

## 12. Model strategy and feasibility gates

WorldState must not hardwire product behavior to one research repository.

### Gate A: geometry

Profile MapAnything, VGGT, and a classical fallback with 2, 4, 8, 16, and 32
views. Record peak VRAM, runtime, output completeness, and reconstruction quality.

### Gate B: segmentation

Profile the live provider and SAM 3.1 on representative short clips. SAM 3.1 is
not an always-on product dependency until it runs reliably within the 8 GB
budget.

### Gate C: scheduling

Prove sequential model loading, CPU offload, and artifact handoff before
attempting concurrent foundation-model residency.

### Gate D: native code

Only move a component to C++/CUDA after profiling shows that it materially
limits throughput or memory.

### Gate E: phone capture

Start with uploaded phone video. Add local network capture only after secure
origin, pairing, transport, and deletion behavior are specified and tested.

## 13. Storage and privacy

- Bind the API to `127.0.0.1` by default.
- Enforce an exact browser-origin allowlist.
- Do not persist continuous webcam video by default.
- Store selected evidence only when the scene policy permits it.
- Keep demographic and sensitive-trait inference out of scope.
- Treat people and hands as transient agents.
- Record every outbound model or telemetry dependency; default to none.
- Provide scene export, retention summary, and complete deletion controls.
- Never expose absolute local paths in API responses.
- Hash artifacts and datasets without logging raw frames.
- Require a new threat review before LAN or public binding.

## 14. Visual direction

WorldState uses a restrained spatial-instrument aesthetic rather than copying a
film interface.

The signature is the **memory volume**: a confidence-aware field of points and
surfaces that moves between observed, uncertain, historical, and missing states.

Palette:

- Black glass: `#08100f`
- Deep scan: `#0d1a18`
- Mineral: `#1d2b28`
- Lumen: `#b5f2e7`
- Archive amber: `#f0a86b`
- Memory violet: `#a8a0e8`
- Bone: `#eaf0ec`

Typography:

- Familjen Grotesk for product and display text.
- JetBrains Mono for telemetry, timestamps, evidence, and measurements.

Layout:

- Dominant world viewport.
- Narrow system rail for scene and model state.
- Bottom temporal instrument for historical state.
- Object Memory appears contextually rather than permanently consuming space.

Motion:

- One orchestrated scan-to-memory transition.
- State changes interpolate rather than pop.
- Reduced-motion mode removes ambient movement and preserves functional state.

## 15. Accessibility

- All gesture actions have mouse, keyboard, and touch alternatives.
- Focus is always visible.
- Canvas interactions expose an accessible parallel object list.
- Color is never the only event or confidence signal.
- Live changes use polite announcements rather than constant interruption.
- The interface remains useful when motion is reduced or the camera is denied.

## 16. Performance targets

These are targets, not current claims:

- No unbounded live frame queue.
- Live input-to-overlay p95 at or below 150 ms on the target laptop.
- At least 8 useful live perception updates per second.
- Viewer rendering at 60 FPS when idle and at least 45 FPS during normal
  interaction.
- GPU peak below 7.5 GB during supported 8 GB workflows.
- No more than one accidental HoloConsole activation per five-minute evaluation
  session.
- At least 95% successful deliberate select gestures in the controlled gesture
  test set.
- Complete scan cancellation and recovery without restarting the application.
- Every published benchmark includes hardware and configuration provenance.

## 17. Research program

### 17.1 Guaranteed output

A paper-style technical report with reproducible experiments. An arXiv preprint
or workshop/conference submission is optional and depends on demonstrated
novelty and results.

### 17.2 Research focus

> Active, uncertainty-aware persistent object memory for changing desk-scale
> environments using consumer monocular RGB cameras.

### 17.3 Hypotheses

`H1` Confidence-weighted semantic and geometric fusion improves persistent
object association over semantics-first, geometry-first, and naive fusion.

`H2` Uncertainty-guided viewpoint suggestions reach a target reconstruction and
object-recall quality using fewer frames than uniform or unguided capture.

`H3` Explicit occlusion states and confidence decay reduce false "still present"
claims without materially reducing rediscovery accuracy.

### 17.4 Baselines

1. Latest-frame-only perception.
2. Naive multiview majority vote.
3. Semantics-first track-and-lift.
4. Geometry-first cluster-and-label.
5. WorldState hybrid fusion.
6. Hybrid without uncertainty weighting.
7. Hybrid without temporal confidence decay.
8. Guided, random, uniform, and unguided keyframe selection.

### 17.5 Dataset strategy

Use:

1. A public indoor reconstruction dataset for geometry and semantic baselines.
2. A custom WorldState Desk Change Set with controlled:
   - additions;
   - removals;
   - translations;
   - rotations;
   - temporary occlusions;
   - rediscovery;
   - visually similar replacements;
   - poor lighting;
   - blur;
   - partial coverage.

Ground truth may use manual annotations, physical measurements, and optional
printable fiducial markers. Specialized camera hardware is not required.

### 17.6 Metrics

Geometry:

- ATE and RPE.
- Depth AbsRel and RMSE.
- Chamfer distance and F-score.

Perception and memory:

- 2D and 3D IoU.
- Object precision and recall.
- Cross-session IDF1 and identity switches.
- Rediscovery accuracy.
- False persistence rate.
- Added, moved, and removed F1.
- Time to detect change.
- Spatial-relation accuracy.

Uncertainty:

- Expected calibration error.
- Brier score.
- Risk-coverage curves.

Active capture:

- Quality versus frame count.
- Quality versus capture time.
- Coverage gain per suggested viewpoint.
- Rejected-frame rate.

Systems:

- p50 and p95 latency.
- Peak VRAM and system RAM.
- Processing time per scan.
- Model-loading overhead.
- Artifact size.
- Native-extension speedup.

### 17.7 Ablations

- No appearance embeddings.
- No geometry term.
- No semantic term.
- No confidence decay.
- No static/dynamic separation.
- No active guidance.
- Random instead of selected keyframes.
- FP32 versus BF16/FP16.
- Python versus native fusion.
- Different input-view counts.

### 17.8 Related-work boundary

WorldState will compare against and cite existing open-vocabulary 3D scene graph,
dynamic mapping, and active-view literature. It will not claim that lifting 2D
foundation-model output into a 3D graph is itself novel.

### 17.9 Paper structure

1. Abstract
2. Introduction
3. Related work
4. Problem definition
5. WorldState method
6. System implementation
7. Experimental protocol
8. Results
9. Ablations
10. Limitations and privacy
11. Conclusion
12. Reproduction appendix

## 18. Verification strategy

### Model-free CI

- Python formatting and lint.
- Static type checking.
- Unit and property tests.
- API tests.
- Frontend lint, type check, unit tests, and production build.
- Dependency lock consistency.
- Secret scanning and dependency review where available.

### Local GPU verification

- Model-access and checkpoint checks.
- Real inference smoke tests.
- Fixed-fixture benchmarks.
- VRAM and latency profiling.
- Browser end-to-end capture and cancellation.
- Gesture accuracy and false-activation evaluation.

### Test fixtures

- Fully synthetic transport and geometry fixtures.
- Licensed recorded video fixtures.
- Explicitly ignored private capture data.
- Dataset manifests containing provenance and hashes.

## 19. Observability

- Structured local logs with session and job IDs.
- No raw image data in logs.
- Per-stage latency and memory measurements.
- Queue depth and skipped-frame counters.
- Model-load and cache state.
- Experiment artifacts linked to exact configuration.
- User-readable diagnostic export.

## 20. Repository and engineering standards

- Strict TypeScript.
- Typed Python with enforced static analysis.
- Small modules organized by domain responsibility.
- Dependency direction enforced: UI and API depend on core; core never depends
  on UI or API.
- No generic `utils.py` dumping ground.
- No hidden global model state outside the scheduler.
- No unrelated model downloads during bootstrap.
- Architecture decisions recorded as ADRs.
- Conventional pull-request checks.
- Apache-2.0 license for original source, with a separate third-party model and
  dataset license record.

## 21. Delivery phases

### Phase 0: foundation

- Approved product specification.
- Typed monorepo.
- Core domain and provider interfaces.
- API and 3D frontend shells.
- Test and CI foundation.
- Privacy, architecture, design, research, and development documentation.

Exit: a new contributor can bootstrap, verify, understand boundaries, and start
the first feasibility spike.

### Phase 1: feasibility and capture

- Camera lifecycle.
- Binary live protocol.
- Bounded frame scheduling.
- Geometry and segmentation profiling.
- Keyframe-quality scoring.

Exit: one model path runs within measured hardware limits and produces typed
observations.

### Phase 2: persistent 2D/2.5D memory

- Entity association.
- Presence lifecycle.
- Confidence decay.
- Object Memory.
- Basic changes, last-seen search, and evidence.

Exit: the fixed-webcam desk-change benchmark runs reproducibly.

### Phase 3: spatial scan

- Multiview reconstruction.
- Semantic lifting.
- Static/dynamic separation.
- Scan alignment.
- Point/surfel viewer.

Exit: a short consumer RGB video produces a queryable spatial scene.

### Phase 4: temporal and active perception

- Ghost Mode.
- Time Scrubber.
- X-ray Memory.
- Active Scan Coach.
- Research baselines and ablations.

Exit: the north-star change and guidance flow works end to end.

### Phase 5: HoloConsole

- Client-side hand tracking.
- Stable one- and two-hand controls.
- Gesture evaluation.
- Accessible input parity.

Exit: the full 60-second flagship demonstration is reliable.

### Phase 6: optimization and publication

- Native performance component.
- Complete benchmark suite.
- Paper figures and report.
- Recorded showcase and portfolio integration.

Exit: every public claim is backed by a reproducible artifact.

## 22. Principal risks

### Model memory exceeds 8 GB

Mitigation: profile before integration, use smaller providers, reduce views,
enable mixed precision and CPU offload, and schedule models sequentially.

### Monocular scale drifts

Mitigation: label approximate scale, compare learned and classical methods, and
support optional calibration markers.

### Dynamic objects corrupt reconstruction

Mitigation: mask transient and movable regions before static fusion and keep
object geometry in a separate layer.

### Object identity switches

Mitigation: combine semantic, appearance, temporal, geometric, and dimensional
evidence; preserve unresolved hypotheses.

### Gesture controls look impressive but feel unreliable

Mitigation: delay HoloConsole until the world model is stable; use deliberate
activation, smoothing, hysteresis, cancellation, and measured gesture tests.

### Research scope is not academically novel

Mitigation: guarantee a rigorous technical report, run a formal related-work
review before publication claims, and focus experiments on active capture and
persistent change under consumer constraints.

### Feature volume delays a usable result

Mitigation: enforce phase exit criteria and build the fixed-webcam memory path
before multiview reconstruction or gestures.

## 23. Approved decisions

- Product name: WorldState.
- HoloConsole is an integrated mode, not a separate project.
- Webcam-first; ordinary phone or uploaded video for optional moving-camera
  scans.
- No special camera required.
- One desk/workspace is the initial product environment.
- Local-first processing and persistence.
- Point/voxel geometry is the internal source of truth.
- Splat/surfel rendering provides the holographic visual treatment.
- Static, persistent, transient, and historical layers remain separate.
- Product and research systems share typed interfaces and reproducible
  artifacts.

## 24. Deferred decisions

These are decided by measured feasibility rather than preference:

- The final geometry provider.
- The final live and scan segmentation providers.
- Whether SAM 3.1 is viable on the target GPU.
- Whether an appearance encoder needs both DINOv2 and SigLIP 2.
- The first native C++/CUDA optimization target.
- The public benchmark dataset used for the first report.
- Whether results justify an arXiv or workshop submission.

## 25. Primary references

- MapAnything: <https://github.com/facebookresearch/map-anything>
- VGGT: <https://github.com/facebookresearch/vggt>
- SAM 3: <https://github.com/facebookresearch/sam3>
- SAM 2: <https://github.com/facebookresearch/sam2>
- ConceptGraphs: <https://arxiv.org/abs/2309.16650>
- NeU-NBV: <https://arxiv.org/abs/2303.01284>
- OGScene3D: <https://arxiv.org/abs/2603.16301>
