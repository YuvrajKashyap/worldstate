# Measured status

This file separates implemented capability, design targets, and observed
performance.

## Current ordinary-webcam acceptance (2026-08-03)

This is the current release evidence. The older tables below are retained as
regression history; synthetic and replay measurements are not evidence that a
live webcam scene is complete.

| Gate | Current status | Evidence |
| --- | --- | --- |
| Exact source isolation | passed | The final session was `browser-webcam`/`live`; zero synthetic sessions contributed to its scene. Synthetic warm-up was removed from application start-up. |
| Raw-frame retention | passed | 13 durable sampled frame records and 103 observations were written for session `019fc6c3-2669-7cd0-ba0a-0a61eeb14c58`; all frame `artifact_id` values were null and no camera images were retained. |
| Session finalization | passed | The latest three live sessions were `completed` after graceful camera/API shutdown. |
| 640x360 live transport | passed | Browser frames used the lossless I420 binary envelope and strict one-frame-in-flight backpressure. |
| p95 capture-to-result <=150 ms | passed in the final 30-second interactive gate | 125 ms p95 over 213 consecutive results; the extended rolling display ended near 135 ms p95. Provider p95 was 13.9 ms, result packing p95 was 1.6 ms, and result-to-next-capture p95 was 0.1 ms. |
| >=8 useful updates/s | **failed** | 213 results in 30.063 seconds, or 7.085 useful updates/s (11.4% below the gate). |
| Visible-object completeness | **failed** | The final view rendered mouse, keyboard, sticky note, bottle, two cups, whiteboard, paper, box, notebook, and wallet. Earbuds, keys, a person, a phone in the person's hand, and small wall items were not all present in the final rendered state. Earlier passes finding an item do not count as final-frame completeness. |
| Relative spacing and support height | partially passed | The world view rendered two inferred support tiers and relative 2.5D bounds. A fixed, uncalibrated monocular webcam cannot establish exact metric depth, object dimensions, or hidden surfaces; the UI labels this geometry as inferred. |
| Physical motion/occlusion acceptance | not run | No operator was available for a deliberate move/remove/occlude script during the final gate. |
| Python verification | passed | 141 tests passed, 89.34% branch-aware coverage, Ruff clean, Pyright 0 errors/0 warnings, and Alembic upgrade/check/downgrade/upgrade passed. |
| Web verification | passed | 157 tests across 25 files; 86.65% statements, 75.72% branches, 90.29% functions, and 86.50% lines, plus lint, strict typecheck, and production build. |
| JavaScript vulnerability audit | passed | `pnpm audit --audit-level high` reported no known vulnerabilities. |
| Python vulnerability audit | **failed** | `pip-audit --skip-editable` reported seven advisories across `setuptools` 81.0.0 and `transformers` 4.57.6. Four local/non-PyPI vision packages could not be audited. |
| Configured Python license gate | passed with caveat | The configured exact-name GPL/AGPL gate exited zero. The full optional geometry environment still contains packages whose metadata identifies GPL variants, so this is not a claim that every optional package is permissively licensed. |

The current product is materially more faithful and durable, but the failed
throughput and completeness gates mean it must not be described as perfect or
as capturing everything. The learned open-vocabulary detector can only report
what it resolves in the pixels; tiny, blurred, low-contrast, or occluded items
remain failure cases. Startup on the measured machine takes roughly 56-66
seconds while the local models are verified and loaded.

| Gate | Status | Evidence |
| --- | --- | --- |
| CPU replay/API workflow | passed on 2026-07-31 | 110 pytest tests passed with 88.61% total coverage |
| OpenCV classical provider smoke | passed on 2026-07-30 | provider contract test in the CPU suite |
| Static analysis | passed on 2026-07-31 | Ruff clean and Pyright at 0 errors |
| Schema and migration compatibility | passed on 2026-07-31 | generated-contract check and Alembic upgrade/check/downgrade/upgrade |
| Claude frontend compatibility | passed on 2026-07-31 | lint, strict typecheck, 123 tests, 89.03% statement coverage, and production build |
| Dependency vulnerability audit | passed on 2026-07-31 | `pip-audit --skip-editable`: no known vulnerabilities |
| JavaScript vulnerability audit | passed on 2026-07-31 | `pnpm audit --audit-level high`: no known vulnerabilities |
| Default dependency license gate | passed on 2026-07-31 | no GPL or AGPL Python package detected by `pip-licenses` |
| Replay provider overhead, 640x360 | 74,483.27 FPS; 0.0133 ms mean on 2026-07-30 | 240 deterministic replay frames; this is not learned-model performance |
| PyTorch/CUDA import in Ubuntu 24.04 | passed on 2026-07-30 | PyTorch 2.11.0+cu128, CUDA 12.8, RTX 4060 Laptop GPU |
| all six local model assets | passed on 2026-07-30 | Grounding DINO, SAM 2.1, DINOv2, Depth Anything V2, MapAnything Apache, and MediaPipe Hand Landmarker verified against the machine-local SHA-256 lock |
| learned dynamic tracking, 640x360 synthetic | 60.785 FPS, 16.45 ms mean, 33.31 ms p95 on 2026-07-31 | 180 moving CUDA frames through asynchronous discovery plus optical-flow propagation; 100% synthetic identity coverage and 0.057 px p95 center error |
| learned provider peak VRAM | passed on 2026-07-31 | 2,406 MiB peak allocated and 2,500 MiB peak reserved in the direct dynamic benchmark |
| supervised persistent worker | passed on 2026-07-30 | explicit warm-up, shared-memory inference, session reset, second inference, and clean teardown |
| MapAnything two-view reconstruction | passed on 2026-07-30 | two synthetic 224x224 views, 4,822 MiB peak allocated, 4,862 MiB peak reserved |
| full production live + scan workflow | passed repo-locally on 2026-07-31 | same-origin UI/security bootstrap, local gesture asset, three learned WebSocket sessions, successful two-keyframe scan, two geometry artifacts, worker suspend/restore, and scene cleanup |
| live 640x360, at least 8 useful updates/s | passed in 30-second pre-soak on 2026-07-30 | 8.017 updates/s through decode, learned inference, temporal persistence, and WebSocket response |
| p95 frame result at or below 150 ms | passed in 30-second pre-soak on 2026-07-30 | 123.38 ms end-to-end p95; provider inference p95 81.42 ms |
| total observed GPU memory below 7.5 GB | passed in 30-second pre-soak on 2026-07-30 | 4,048 MiB maximum total GPU memory observed by `nvidia-smi` |
| first 30-minute live soak | memory passed; performance failed on 2026-07-31 | 13,975 frames; RAM/VRAM slopes were flat, but 7.760 updates/s and 173.54 ms p95 missed the live gates |
| optimized five-minute sustained gate | passed on 2026-07-31 | 2,939 frames; 9.791 updates/s, 106.12 ms p95, 4,056 MiB maximum sampled GPU memory, and flat RAM/VRAM slopes |
| historical 30-minute soak before the low-latency tracker | passed on 2026-07-31 | 15,606 frames over 1,800.75 seconds; 8.666 useful updates/s, 146.61 ms end-to-end p95, and flat memory; retained as regression history, not current performance |
| low-latency learned soak, repo-local data | passed on 2026-07-31 | 5,596 frames over 180.01 seconds; 31.087 useful updates/s, 20.10 ms median, 40.17 ms p95, 18.10 ms provider p95, 100% synthetic identity coverage, 0.268 px p95 center error, 2,588 MiB flat worker-reserved VRAM, and stable API/worker RSS |
| current low-latency 30-minute soak | passed on 2026-07-31 | 55,689 learned frames over 1,800.49 seconds; 30.930 useful updates/s, 24.45 ms median, 33.69 ms p95, 19.43 ms provider p95, 100% synthetic identity coverage, 0.277 px p95 center error, 2,588 MiB flat worker-reserved VRAM, 0.346 MiB/min API RSS slope, and 0.406 MiB/min worker RSS slope |
| change-event F1 at least 0.85 | target only | Desk Change Set not captured |
| IDF1 at least 0.75 | target only | Desk Change Set not captured |
| last-seen error at or below one second | target only | Desk Change Set not captured |
| guided scan success and calibrated scale targets | target only | requires the private 12-session capture set and a physical reference measurement |

The current repo-local low-latency report is
`.worldstate/benchmarks/dynamic-e2e-soak-final-write-behind-30m.json` with
SHA-256
`2b3fe309c3075ffd183ab17e54a4d535480f5ce5aff06fc6ffbcd316246b3282`.

## Verification environment

- Date: 2026-07-31
- Platform: Windows 11 build 26200
- GPU observed by diagnostics: NVIDIA GeForce RTX 4060 Laptop GPU, 8,188 MiB,
  driver 592.82
- Python: 3.12.13
- Node.js: 24.12.0
- pnpm: 10.33.0
- uv: 0.11.6
- Git revision before the implementation worktree:
  `7b819f9203cab735ce5502f98ba04fa4b74378a7`
- Worktree: dirty by design; this implementation is not committed or pushed
- WSL runtime: Ubuntu 24.04.4 LTS under WSL2
- Learned runtime: PyTorch 2.11.0+cu128 and CUDA 12.8
- Model storage: 6.3 GB under repository-local `.worldstate/models`
- Model lock SHA-256:
  `0dd27568503a0e291bffd203f64d6665bd6ef3ec881382796e0ff842ccb589e3`
- Transactional database, artifacts, uploads, exports, and model weights:
  repository-local `.worldstate/` with a 75 GB logical quota

## Reproduction

```powershell
.\scripts\verify.ps1
uv run pip-audit --skip-editable
uv run pip-licenses --fail-on="GNU Affero General Public License;GNU General Public License"
pnpm --filter @worldstate/contracts check
uv run worldstate doctor --json
uv run worldstate benchmark --frames 240 --width 640 --height 360
uv run python scripts/gpu-smoke.py live-benchmark --frames 32
uv run python scripts/gpu-smoke.py supervised-worker
uv run python scripts/gpu-smoke.py map-infer
uv run python scripts/production-smoke.py --token <one-time-token> --include-scan
.\scripts\live-soak.ps1 -Token <one-time-token> -DurationSeconds 1800 -TargetFps 60
```

Do not convert a target to "passed" without a dated report containing the Git
revision, dirty state, environment, model hashes, dataset hashes, seed, raw
samples, and reproduction command.
