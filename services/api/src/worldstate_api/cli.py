# pyright: basic, reportMissingImports=false
"""Operational CLI for local WorldState administration."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Annotated, cast
from urllib.parse import urlparse

import numpy as np
import typer

from worldstate_api.evaluation import evaluate_manifest, provenance
from worldstate_api.persistence import Database
from worldstate_api.providers.registry import ModelRegistry, ModelSpec
from worldstate_api.providers.replay import ReplayPerceptionProvider
from worldstate_api.settings import Settings

app = typer.Typer(
    name="worldstate",
    help="Operate the local-first WorldState backend.",
    no_args_is_help=True,
)
models_app = typer.Typer(help="Inspect and explicitly acquire pinned models.")
database_app = typer.Typer(help="Inspect and repair the local database.")
app.add_typer(models_app, name="models")
app.add_typer(database_app, name="db")

_SAM_CONFIG_PATH = "sam2/configs/sam2.1/sam2.1_hiera_t.yaml"
_SAM_CHECKPOINT_NAME = "sam2.1_hiera_tiny.pt"
_DIRECT_MODEL_FILENAMES = {
    "mediapipe-hand-landmarker": "hand_landmarker.task",
}


def _settings() -> Settings:
    return Settings()


def _registry(settings: Settings) -> ModelRegistry:
    return ModelRegistry(
        manifest_path=settings.model_manifest_path,
        lock_path=settings.model_lock_path,
        models_root=settings.models_root,
    )


def _hash_files(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if ".cache" in path.parts:
            continue
        files[path.relative_to(root).as_posix()] = ModelRegistry.hash_file(path)
    if not files:
        raise RuntimeError("the acquired model directory contains no files")
    return files


def _write_lock(settings: Settings, registry: ModelRegistry) -> None:
    existing: dict[str, object] = {}
    if settings.model_lock_path.is_file():
        payload = json.loads(settings.model_lock_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and isinstance(payload.get("models"), dict):
            existing = dict(payload["models"])
    for spec in registry.specs():
        model_path = (settings.models_root / spec.relative_path).resolve()
        if model_path.is_dir():
            existing[spec.id] = {
                "revision": spec.revision,
                "files": _hash_files(model_path),
            }
    settings.model_lock_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = settings.model_lock_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"schema_version": 1, "models": existing}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, settings.model_lock_path)


def _download_https(url: str, destination: Path) -> None:
    parsed = urlparse(url)
    allowed_hosts = {
        "dl.fbaipublicfiles.com",
        "raw.githubusercontent.com",
        "storage.googleapis.com",
    }
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts:
        raise RuntimeError("the manifest URL is outside the model-source allowlist")
    request = urllib.request.Request(url, headers={"User-Agent": "WorldState/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname not in allowed_hosts:
            raise RuntimeError("the model download redirected outside the source allowlist")
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)


def _acquire(spec: ModelSpec, destination: Path) -> None:
    if spec.source.startswith("hf://"):
        try:
            from huggingface_hub import snapshot_download
        except ImportError as error:
            raise RuntimeError(
                "Install the vision extra before acquiring Hugging Face models."
            ) from error
        repository_id = spec.source.removeprefix("hf://")
        snapshot_download(
            repo_id=repository_id,
            revision=spec.revision,
            local_dir=destination,
            local_files_only=False,
        )
        cache = destination / ".cache"
        if cache.exists():
            shutil.rmtree(cache)
        return
    direct_filename = _DIRECT_MODEL_FILENAMES.get(spec.id)
    if direct_filename is not None:
        _download_https(spec.source, destination / direct_filename)
        return
    if spec.id != "sam2.1-hiera-tiny":
        raise RuntimeError("unsupported non-Hugging-Face model source")
    _download_https(spec.source, destination / _SAM_CHECKPOINT_NAME)
    config_url = (
        "https://raw.githubusercontent.com/facebookresearch/sam2/"
        f"{spec.revision}/{_SAM_CONFIG_PATH}"
    )
    _download_https(config_url, destination / "sam2.1_hiera_t.yaml")


@app.command()
def doctor(
    as_json: Annotated[bool, typer.Option("--json", help="Emit machine-readable output.")] = False,
) -> None:
    """Check local runtime, storage, GPU, and model readiness without changing state."""

    settings = _settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(settings.data_root)
    gpu: dict[str, object] = {"available": False}
    try:
        output = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        if output:
            name, memory_mib, driver = [part.strip() for part in output.splitlines()[0].split(",")]
            gpu = {
                "available": True,
                "name": name,
                "memory_mib": int(memory_mib),
                "driver": driver,
            }
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    model_rows = [item.model_dump(mode="json") for item in _registry(settings).list_models()]
    report: dict[str, object] = {
        "ok": disk.free >= 5_000_000_000,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "wsl": bool(os.environ.get("WSL_DISTRO_NAME")),
        "data_root_exists": settings.data_root.is_dir(),
        "storage_free_bytes": disk.free,
        "storage_quota_bytes": settings.storage_quota_bytes,
        "gpu": gpu,
        "models": model_rows,
    }
    if as_json:
        typer.echo(json.dumps(report, indent=2))
    else:
        typer.echo(f"WorldState doctor: {'ready' if report['ok'] else 'attention required'}")
        typer.echo(f"Python {report['python']} | WSL: {report['wsl']}")
        typer.echo(f"Storage free: {disk.free / 1_000_000_000:.1f} GB")
        typer.echo(f"GPU: {gpu.get('name', 'not detected')}")
        for model in model_rows:
            typer.echo(f"  {model['id']}: {model['state']}")
    if not report["ok"]:
        raise typer.Exit(code=1)


@models_app.command("list")
def list_models() -> None:
    """List pinned model license and local verification state."""

    for model in _registry(_settings()).list_models():
        typer.echo(f"{model.id}\t{model.state.value}\t{model.license}\t{model.revision[:12]}")


@models_app.command("verify")
def verify_models() -> None:
    """Verify all installed model files against the local SHA-256 lock."""

    models = _registry(_settings()).list_models()
    for model in models:
        typer.echo(f"{model.id}: {model.state.value}")
    if any(model.required and model.state.value != "available" for model in models):
        raise typer.Exit(code=1)


@models_app.command("install")
def install_model(
    model_id: Annotated[
        str,
        typer.Argument(help="Allowlisted model ID from configs/models.yaml."),
    ],
    force: Annotated[bool, typer.Option(help="Replace an existing local model.")] = False,
) -> None:
    """Explicitly download one immutable manifest-pinned model and write its lock."""

    settings = _settings()
    registry = _registry(settings)
    spec = registry.get_spec(model_id)
    destination = (settings.models_root / spec.relative_path).resolve()
    if destination.exists() and not force:
        raise typer.BadParameter("model directory exists; verify it or pass --force")
    settings.models_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{spec.id}-", dir=settings.models_root) as temp:
        temporary = Path(temp)
        typer.echo(f"Acquiring {spec.display_name} at revision {spec.revision}...")
        _acquire(spec, temporary)
        if destination.exists():
            shutil.rmtree(destination)
        temporary.replace(destination)
    _write_lock(settings, registry)
    refreshed = _registry(settings)
    if refreshed.verify(refreshed.get_spec(model_id)).value != "available":
        raise RuntimeError("downloaded model failed verification")
    typer.echo(f"Verified {model_id}.")


@models_app.command("install-defaults")
def install_defaults(
    include_reconstruction: Annotated[
        bool,
        typer.Option(help="Also acquire the much larger MapAnything checkpoint."),
    ] = False,
) -> None:
    """Acquire live and gesture defaults; MapAnything remains opt-in due to size."""

    registry = _registry(_settings())
    for spec in registry.specs():
        if spec.id == "map-anything-apache" and not include_reconstruction:
            continue
        install_model(spec.id, force=False)


@database_app.command("repair")
def repair_database() -> None:
    """Create missing schema objects and mark interrupted jobs as failed."""

    settings = _settings()
    database = Database(settings.database_url)
    try:
        database.create_schema()
        recovered = database.recover_interrupted_jobs()
        if not database.ping():
            raise RuntimeError("database health check failed")
    finally:
        database.dispose()
    typer.echo(f"Database ready; recovered {recovered} interrupted job(s).")


@app.command()
def benchmark(
    frames: Annotated[int, typer.Option(min=10, max=10_000)] = 240,
    width: Annotated[int, typer.Option(min=320, max=1920)] = 640,
    height: Annotated[int, typer.Option(min=240, max=1080)] = 360,
) -> None:
    """Measure deterministic coordinator/provider overhead without claiming GPU performance."""

    provider = ReplayPerceptionProvider()
    image = np.zeros((height, width, 3), dtype=np.uint8)
    samples: list[float] = []
    started = time.perf_counter()
    for sequence in range(frames):
        before = time.perf_counter()
        provider.observe(image, sequence=sequence, prompts=("cup", "book", "phone"))
        samples.append((time.perf_counter() - before) * 1000)
    duration = time.perf_counter() - started
    report = {
        "provider": provider.provider_id,
        "frames": frames,
        "resolution": [width, height],
        "throughput_fps": frames / duration,
        "mean_provider_ms": sum(samples) / len(samples),
        "scope": "deterministic replay provider; not learned-model performance",
    }
    typer.echo(json.dumps(report, indent=2))


@app.command()
def evaluate(
    manifest: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path | None, typer.Option(help="Optional JSON report path.")] = None,
) -> None:
    """Run a deterministic versioned evaluation manifest."""

    raw = manifest.read_bytes()
    payload_object: object = json.loads(raw)
    if not isinstance(payload_object, dict):
        raise typer.BadParameter("manifest must contain a JSON object")
    payload = cast(dict[str, object], payload_object)
    metrics = evaluate_manifest(payload)
    report = {
        "schema_version": 1,
        "metrics": metrics,
        "provenance": provenance(
            config={"manifest": manifest.name},
            dataset_hash=hashlib.sha256(raw).hexdigest(),
        ),
    }
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized, encoding="utf-8")
    typer.echo(serialized)


@app.command()
def serve() -> None:
    """Run the secured same-origin production server."""

    import uvicorn

    settings = _settings()
    uvicorn.run(
        "worldstate_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
