# WorldState

**A persistent visual memory for physical spaces.**

WorldState is a local-first spatial-computing system that turns ordinary webcam
and phone video into a persistent, queryable model of a physical workspace. It
separates static geometry, movable objects, transient agents, and historical
memory so it can explain what exists, what changed, how certain it is, and which
observations support that conclusion.

This repository currently contains the approved product specification and the
model-free engineering foundation. Accuracy and performance claims will only be
published after labeled, reproducible evaluation.

## Product direction

- Live webcam memory for a desk or workspace.
- Optional multi-view reconstruction from ordinary RGB video.
- Added, moved, removed, occluded, and rediscovered object events.
- Ghost Mode, Time Scrubber, Change Pulses, Object Memory, Uncertainty View,
  animated Scene Graph, and Last-Seen Search.
- Active Scan Coach for uncertainty-guided capture.
- HoloConsole for deliberate two-hand spatial interaction.
- Local evidence, provenance, and research-grade evaluation.

Read the complete [product specification](product_spec.md).

## Repository map

```text
apps/web/                    React and Three.js spatial interface
services/api/                FastAPI coordinator
packages/worldstate-core/    Framework-independent domain and provider ports
configs/                     Versioned product and experiment configuration
datasets/                    Dataset manifests; private captures are ignored
docs/                        Architecture, privacy, design, and decisions
experiments/                 Reproducible experiment entrypoints and results
native/                      Future measured C++/CUDA optimization
paper/                       Technical-report source and reproduction notes
scripts/                     Bootstrap, development, and verification commands
```

## Prerequisites

- Windows 11
- Node.js 22 or newer
- pnpm 10
- uv
- Python 3.12, installed automatically by the bootstrap script when possible

CUDA models are deliberately not downloaded during bootstrap.

## Bootstrap

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

## Develop

Start the API:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev-api.ps1
```

Start the interface in another terminal:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev-web.ps1
```

Open `http://127.0.0.1:5173`.

## Verify

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

The default verification path is model-free and suitable for CI. GPU
feasibility, model access, latency, VRAM, and accuracy are separate measured
gates.

## Privacy boundary

WorldState binds locally by default, does not persist continuous webcam video,
does not create persistent biometric identities, and does not infer sensitive
personal traits from appearance. See [Privacy](docs/PRIVACY.md) and the
[threat model](docs/THREAT_MODEL.md).

## License

Original source is licensed under Apache-2.0. Model weights, datasets, fonts, and
other third-party artifacts retain their own licenses and are not covered by
the project license.
