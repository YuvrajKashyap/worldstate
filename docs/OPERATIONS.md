# Operations and troubleshooting

## Normal paths

```powershell
.\scripts\bootstrap.ps1
.\scripts\doctor.ps1
.\scripts\setup-wsl.ps1
.\scripts\models.ps1 -Defaults -IncludeReconstruction
.\scripts\run.ps1
```

`run.ps1` builds Claude's frontend and starts the WSL backend on loopback. The
browser opens with a one-time fragment capability. Data defaults to
the repository-local `C:\Users\ykyuv\dev\worldstate\.worldstate` directory
(`/mnt/c/Users/ykyuv/dev/worldstate/.worldstate` in WSL) with a logical 75 GB
quota. Models, SQLite state, uploads, exports, and artifacts remain together
there and the directory is Git-ignored. The
production launcher defaults to the learned provider and fails closed during
startup if its explicitly acquired, checksum-pinned models are unavailable.
Use the separate development launchers for replay or classical mode.

For model-free development, run `scripts/dev-api.ps1` and
`scripts/dev-web.ps1` in separate terminals and use replay mode.

## Diagnostics

`worldstate doctor --json` reports Python, WSL, disk, GPU, and model lock state
without returning absolute paths through the HTTP API. `/api/v1/diagnostics`
adds runtime memory, database, artifact, and GPU availability for an
authenticated browser session.

## Common failures

| Symptom | Action |
| --- | --- |
| `Ubuntu-24.04 is not ready` | run `setup-wsl.ps1`, reboot if Windows asks, open Ubuntu once, rerun |
| `nvidia-smi` absent in WSL | update the NVIDIA Windows driver; do not install a Linux display driver |
| model is `not_installed` | explicitly run `models.ps1 -Defaults -IncludeReconstruction` |
| model is `invalid` | do not bypass the check; reacquire with the CLI after reviewing free space |
| scan reports `depth_assisted_open3d_relative_scale` | MapAnything exhausted GPU memory; approximate local fallback geometry was returned |
| scan reports `keyframes_only` | verify both MapAnything and Depth Anything; the final degraded output is intentional |
| API returns origin/CSRF rejection | use only the launcher/Vite origins and memory-held CSRF returned by bootstrap |
| job says `runtime_restarted` | the previous process ended mid-job; safely submit a new job |
| storage is full | export needed scenes, delete unwanted scenes, then run authorized garbage collection |

## Recovery and deletion

`worldstate db repair` creates missing schema objects, verifies SQLite, and
marks interrupted work failed without inventing a success. Scene deletion
cascades relational state, decrements owned artifact references, then runs
verified orphan collection. Exported files copied outside the WorldState data
root remain the operator's responsibility.

## Production boundaries

Do not bind to `0.0.0.0`, forward the port, expose it through a tunnel, or host
the GPU API. The public portfolio should use a recorded video or the
deterministic replay fixture. Production disables interactive API docs.
