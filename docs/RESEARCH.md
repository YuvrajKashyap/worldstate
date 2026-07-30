# Research program

WorldState guarantees a reproducible paper-style technical report. An arXiv
preprint or peer-reviewed submission is conditional on results and a formal
novelty review.

## Research question

> Can active, uncertainty-aware semantic and geometric fusion improve persistent
> object memory in changing desk-scale environments captured by consumer
> monocular RGB cameras?

## Hypotheses

- **H1:** Confidence-weighted fusion improves persistent association over
  semantics-first, geometry-first, and naive multiview baselines.
- **H2:** Uncertainty-guided viewpoints reach target quality with fewer frames
  than uniform, random, or unguided capture.
- **H3:** Explicit occlusion and confidence decay reduce false persistence
  without materially reducing rediscovery accuracy.

## Reproducibility contract

Every experiment records:

- Git commit.
- Dirty-worktree state.
- Configuration hash.
- Dataset and input hashes.
- Model repository, revision, and checkpoint hash.
- Python, PyTorch, CUDA, driver, and dependency versions.
- CPU, GPU, RAM, and operating environment.
- Random seeds.
- Warm-up and measurement protocol.
- Raw per-sample results.

Results without this information are exploratory and must not appear as public
claims.

## Baselines

1. Latest frame only.
2. Naive multiview vote.
3. Semantics-first track and lift.
4. Geometry-first cluster and label.
5. WorldState hybrid.
6. Hybrid without uncertainty weighting.
7. Hybrid without confidence decay.
8. Guided, uniform, random, and unguided frame selection.

## Related-work boundary

Existing systems already construct open-vocabulary 3D scene graphs and perform
uncertainty-guided view planning. The initial related-work set includes:

- ConceptGraphs: <https://arxiv.org/abs/2309.16650>
- NeU-NBV: <https://arxiv.org/abs/2303.01284>
- OGScene3D: <https://arxiv.org/abs/2603.16301>
- HOV-SG: <https://github.com/hovsg/HOV-SG>

WorldState will not call 2D-to-3D semantic lifting novel. Its candidate research
focus is persistent change, explicit belief state, active human guidance, and
consumer hardware constraints.

## Data

The evaluation combines a suitable public indoor dataset with a controlled
WorldState Desk Change Set. Private captures remain outside Git. Dataset
manifests record license, source, checksum, split, and allowed uses.

## Metrics

The complete metric set is defined in [product_spec.md](../product_spec.md).
Metric implementations must be unit tested against small hand-computed fixtures.

## Statistical policy

- Report sample count and distribution.
- Use paired comparisons when methods share inputs.
- Report confidence intervals, not only means.
- Predefine primary metrics before the final evaluation.
- Preserve negative and null results.
- Avoid treating correlated video frames as independent samples.

## Paper source

The eventual report lives under `paper/`. Tables and plots must be generated
from raw experiment artifacts, not transcribed manually.
