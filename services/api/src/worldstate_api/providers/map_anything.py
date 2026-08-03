# pyright: basic, reportMissingImports=false
"""Offline-only MapAnything construction using its pinned vendored DINOv2 code."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_map_anything_local(
    model_path: Path,
    *,
    device: str = "cuda",
    dtype: Any = None,
) -> Any:
    """Load a local checkpoint without allowing Torch Hub network resolution.

    MapAnything's UniCeption encoder calls ``torch.hub.load`` even when
    pretrained encoder weights are disabled. The pinned MapAnything package
    already vendors the exact DINOv2 implementation it needs, so WorldState
    temporarily routes that one factory call to the vendored module and rejects
    every other Torch Hub request.
    """

    import torch
    from mapanything.models import MapAnything
    from mapanything.models.external.dinov2.hub import backbones

    original_load = torch.hub.load
    original_load_state_dict = torch.hub.load_state_dict_from_url

    def local_hub_load(
        repository: str,
        model_name: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        if repository != "facebookresearch/dinov2":
            raise RuntimeError(f"Torch Hub network loading is disabled: {repository}")
        factory = getattr(backbones, model_name, None)
        if factory is None or not callable(factory):
            raise RuntimeError(f"unsupported vendored DINOv2 factory: {model_name}")
        kwargs.pop("force_reload", None)
        kwargs.pop("trust_repo", None)
        kwargs.pop("source", None)
        if kwargs.get("pretrained", False):
            raise RuntimeError("vendored DINOv2 must not download separate weights")
        return factory(*args, **kwargs)

    def reject_remote_weights(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("remote Torch Hub weight loading is disabled")

    torch.hub.load = local_hub_load
    torch.hub.load_state_dict_from_url = reject_remote_weights
    try:
        model = MapAnything.from_pretrained(str(model_path))
    finally:
        torch.hub.load = original_load
        torch.hub.load_state_dict_from_url = original_load_state_dict

    if dtype is None:
        return model.to(device=device).eval()
    return model.to(device=device, dtype=dtype).eval()
