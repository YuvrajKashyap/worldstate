# Model inventory and acquisition

WorldState has three provider modes:

- `replay`: deterministic objects for Claude integration, tests, and demos.
- `classical`: real OpenCV foreground perception with no model downloads.
- `models`: the pinned learned stack below.

No weight is downloaded during import, bootstrap, CI, or inference. The
operator must run `scripts/models.ps1`, which reads `configs/models.yaml`,
acquires only allowlisted sources at immutable revisions, hashes every file,
and writes the machine-local lock under the data root.

| ID | Role | License | Pinned source | Default |
| --- | --- | --- | --- | --- |
| `grounding-dino-tiny` | open-vocabulary discovery | Apache-2.0 | Hugging Face snapshot | live |
| `sam2.1-hiera-tiny` | optional scan/image mask refinement; not used in the latency-critical live box/bounds path | Apache-2.0 | Meta checkpoint and pinned SAM 2 code | optional |
| `dinov2-small` | appearance embeddings | Apache-2.0 | Hugging Face snapshot | live |
| `depth-anything-v2-small` | relative monocular depth | Apache-2.0 | Hugging Face snapshot | live |
| `map-anything-apache` | offline multiview geometry | Apache-2.0 | Apache checkpoint and pinned source | scan, explicit large download |
| `mediapipe-hand-landmarker` | browser-local hand landmarks | Apache-2.0 | Google MediaPipe float16 v1 asset | HoloConsole |

The exact checkpoint revisions, code revisions, approximate sizes, and URLs are
in [configs/models.yaml](../configs/models.yaml) and
[services/api/pyproject.toml](../services/api/pyproject.toml). PyTorch 2.11 and
torchvision 0.26 use the explicit CUDA 12.8 index on Linux. SAM 2 and
MapAnything source dependencies are Git-revision locked by `uv.lock`.

## Commands

```powershell
# Inventory only
.\scripts\models.ps1

# Live models plus the browser-local hand model
.\scripts\models.ps1 -Defaults

# Include the much larger reconstruction checkpoint
.\scripts\models.ps1 -Defaults -IncludeReconstruction
```

Run `worldstate models verify` inside WSL after any storage restore or manual
file change. A changed file becomes `invalid`; runtime loading fails closed.

## Compatibility and fallback

The supported environment is one lockstep set, never a mixture:

- Python 3.12
- PyTorch 2.11
- torchvision 0.26
- CUDA 12.8 wheels
- Ubuntu 24.04 under WSL2

If the real-provider compatibility suite fails, produce a new complete
PyTorch/CUDA lock before changing the shipping environment. The usable fallback
order is learned provider, OpenCV classical provider, then deterministic replay.
Scans unload the live worker before MapAnything claims the GPU, then restore
the warmed live provider after the exclusive job. CUDA exhaustion falls back
to local Depth Anything plus Open3D ICP; unavailable reconstruction providers
degrade explicitly to selected keyframes.

## Measurement status

The current target-machine measurements are recorded in
[Measured status](MEASURED_STATUS.md). They cover pinned-weight integrity,
learned live inference, the supervised worker lifecycle, MapAnything
reconstruction, the production same-origin workflow, and a timed soak. They do
not imply Desk Change Set accuracy.
