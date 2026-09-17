"""
Inference bridge — runs separation on the local GPU stack.

Standalone: separation is performed by the `audio-separator` package, which
bundles its own model architectures (RoFormer, MDXC, Demucs, VR …) and pulls
weights from Hugging Face. No MSST-WebUI checkout is needed.

The worker never uploads audio anywhere; everything runs locally.
"""

from __future__ import annotations

import gc
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from model_manager import manager

logger = logging.getLogger("uvr.inference")

OUTPUT_ROOT = Path(os.environ.get("OUTPUT_ROOT", "./output"))
MODEL_CATALOG_PATH = Path(os.environ.get("MODEL_CATALOG", "./models.json"))

ProgressFn = Callable[[float, str], None]

# Small mtime-keyed caches so frequent /api/models polling stays cheap.
_CATALOG_CACHE: dict[str, Any] = {}


def _read_json_cached(path: Path, cache: dict) -> dict[str, dict[str, Any]]:
    """Read a JSON file, re-reading only when its mtime changes.

    `/api/models` is polled frequently by the UI, so avoid hitting the disk
    (and re-parsing) on every request.
    """
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    if cache.get("mtime") == mtime:
        return cache.get("data", {})
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not read %s: %s", path, exc)
        data = {}
    cache["mtime"] = mtime
    cache["data"] = data
    return data


def _load_catalog() -> dict[str, dict[str, Any]]:
    return _read_json_cached(MODEL_CATALOG_PATH, _CATALOG_CACHE)


def _ensure_config_aliases(model_dir: Path) -> None:
    """Give audio-separator the YAML name it expects.

    Our model store keeps the checkpoint and its config side by side (often
    called `config.yaml`). audio-separator derives the config path from the
    *checkpoint's* basename (`foo.ckpt` -> `foo.yaml`), so without an alias it
    silently falls back to a default architecture and the load fails.
    """
    try:
        yamls = [p for p in model_dir.iterdir() if p.suffix in (".yaml", ".yml")]
    except OSError:
        return
    if not yamls:
        return
    for ckpt in model_dir.iterdir():
        if ckpt.suffix not in (".ckpt", ".pth", ".safetensors", ".th"):
            continue
        alias = ckpt.with_suffix(".yaml")
        if alias.exists():
            continue
        # Prefer a config whose stem matches the checkpoint, else copy the first.
        src = next((y for y in yamls if y.stem == ckpt.stem), yamls[0])
        try:
            shutil.copyfile(src, alias)
        except OSError as exc:  # pragma: no cover
            logger.debug("Could not alias %s -> %s: %s", src, alias, exc)


class _AudioSeparatorBackend:
    """Standalone backend using the `audio-separator` package.

    It ships its own model loaders (RoFormer, MDXC, Demucs, VR …) and reads
    checkpoints from a local directory, so the app needs no external code
    checkout — only the downloaded weights in the managed model store.
    """

    name = "audio-separator"

    def __init__(self) -> None:
        from audio_separator.separator import Separator  # type: ignore

        self._cls = Separator

    def available_models(self) -> list[dict[str, Any]]:
        """Nothing extra to advertise.

        Every model the app can run is declared in `models.json`; this backend
        only executes them, so it contributes no additional catalog entries.
        """
        return []

    def separate(
        self,
        model_id: str,
        input_path: str,
        output_dir: str,
        output_format: str,
        use_tta: bool,
        extract_instrumental: bool,
        progress: ProgressFn,
    ) -> list[dict[str, Any]]:
        rec = manager.get(model_id)
        if rec is not None and rec.downloadable and not manager.is_installed(model_id):
            progress(1, f"Downloading model {rec.name}")
            manager.ensure(
                model_id,
                on_progress=lambda pct, msg: progress(1 + pct * 0.03, msg),
            )

        paths = manager.paths(model_id)

        if paths:
            # Present in the managed store: serve it from disk.
            model_dir: Optional[str] = str(Path(paths["dir"]))
            model_file = Path(paths["model_path"]).name
            _ensure_config_aliases(Path(paths["dir"]))
        else:
            # Not in the managed store. Treat the id as an audio-separator
            # registry filename — the library downloads the weights and its
            # matching YAML config itself, which is the supported path for
            # running without an external checkout.
            model_dir = None
            model_file = model_id

        os.makedirs(output_dir, exist_ok=True)
        sep_kwargs: dict[str, Any] = {
            "output_dir": output_dir,
            "output_format": output_format.upper(),
            "use_autocast": True,
        }
        if model_dir:
            sep_kwargs["model_file_dir"] = model_dir
        sep = self._cls(**sep_kwargs)

        progress(5, "Loading model")
        sep.load_model(model_filename=model_file)

        progress(10, "Running GPU inference")
        start = time.time()
        produced = sep.separate(input_path)
        logger.info("Separation took %.1fs for %s", time.time() - start, model_id)

        stems: list[dict[str, Any]] = []
        files = produced if isinstance(produced, (list, tuple)) else []
        total = max(len(files), 1)
        for i, f in enumerate(files):
            out_path = Path(f if os.path.isabs(str(f)) else os.path.join(output_dir, str(f)))
            if not out_path.exists():
                continue
            # audio-separator names files
            # "<input>_(<Stem>)_<model>.<ext>" — the stem is the parenthesised
            # part. Fall back to the whole stem name if the shape ever differs.
            match = re.search(r"\(([^)]+)\)", out_path.stem)
            stem = match.group(1).strip() if match else out_path.stem
            if extract_instrumental and stem.lower().startswith("vocal"):
                continue
            stems.append(
                {
                    "name": stem,
                    "url": f"/api/jobs/{Path(output_dir).name}/stems/{out_path.name}",
                    "sizeBytes": out_path.stat().st_size,
                    "format": output_format,
                }
            )
            progress(10 + int((i + 1) / total * 85), f"Saved {stem}")

        del sep
        gc.collect()
        progress(100, "Done")
        return stems


_backend: Optional[Any] = None


def get_backend() -> Any:
    """Resolve the inference backend (standalone audio-separator)."""
    global _backend
    if _backend is not None:
        return _backend
    try:
        _backend = _AudioSeparatorBackend()
        logger.info("Using audio-separator backend (%s)", _backend.name)
        return _backend
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "No inference backend available: could not import 'audio-separator'. "
            "It is declared in api/requirements.txt — rebuild the image."
        ) from exc


def list_models() -> list[dict[str, Any]]:
    """Catalog merged with the ModelManager's live install state."""
    merged = manager.list()
    for m in merged:
        m["installedVia"] = "store" if m.get("installed") else None
    known = {m["id"] for m in merged}
    try:
        for m in get_backend().available_models():
            if m["id"] not in known:
                merged.append(
                    {
                        **m,
                        "installed": True,
                        "downloadable": False,
                        "path": "",
                        "sizeBytes": int(m.get("sizeMB", 0) * 1e6),
                        "download": {
                            "status": "installed",
                            "percent": 100.0,
                            "error": None,
                            "receivedBytes": 0,
                            "totalBytes": 0,
                            "speedBps": 0,
                            "etaSec": None,
                        },
                    }
                )
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not discover installed models: %s", exc)
    return merged


def separate_file(
    model_id: str,
    input_path: str,
    output_dir: str,
    output_format: str = "mp3",
    use_tta: bool = False,
    extract_instrumental: bool = False,
    progress: Optional[ProgressFn] = None,
) -> list[dict[str, Any]]:
    progress = progress or (lambda p, s: None)
    backend = get_backend()
    return backend.separate(
        model_id,
        input_path,
        output_dir,
        output_format,
        use_tta,
        extract_instrumental,
        progress,
    )