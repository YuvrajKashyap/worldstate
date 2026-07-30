# Model providers

WorldState has no supported model provider in the foundation release. Provider
selection is a measured feasibility decision.

## Required provider record

Every provider integration must document:

- Capability and adapter interface.
- Upstream repository and immutable revision.
- Checkpoint identifier and checksum.
- Code and weight license.
- Dataset restrictions inherited by the checkpoint.
- Python, PyTorch, CUDA, and system requirements.
- Peak VRAM and system RAM.
- Warm-up and measured latency.
- Input limits.
- Failure and cancellation behavior.
- Product fallback.

## Initial candidates

Geometry:

- MapAnything.
- VGGT.
- PyCOLMAP/COLMAP.
- Depth Anything 3 or MoGe 2 for a lighter depth path.

Perception:

- A bounded-latency live detector and mask provider.
- SAM 3.1 for selected high-quality scan workloads when feasible.
- SAM 2.1 as a smaller video segmentation option.

Appearance:

- DINOv2.
- SigLIP 2 when language alignment is required.

No model is downloaded by bootstrap or CI.
