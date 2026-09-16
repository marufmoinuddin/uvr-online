"""
Inference bridge — runs separation on the local GPU stack.

Backend resolution order:
  1. MSST-WebUI (MSSeparator) — the verified stack in this workspace
  2. pymss (Separator) — drop-in fallback if installed
  3. audio-separator — last-resort fallback

The worker never uploads audio anywhere; everything runs locally.
"""

from __future__ import annotations

import gc
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from model_manager import manager

logger = logging.getLogger("uvr.inference")

MSST_ROOT = os.environ.get("MSST_ROOT", "/home/maruf/git/MSST-WebUI")
OUTPUT_ROOT = Path(os.environ.get("OUTPUT_ROOT", "./output"))
MODEL_CATALOG_PATH = Path(os.environ.get("MODEL_CATALOG", "./models.json"))

ProgressFn = Callable[[float, str], None]

# Small mtime-keyed caches so frequent /api/models polling stays cheap.
_CATALOG_CACHE: dict[str, Any] = {}
_MSST_INFO_CACHE: dict[str, Any] = {}


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


def _load_msst_models_info() -> dict[str, dict[str, Any]]:
    """Read MSST's models_info.json to resolve installed checkpoints."""
    return _read_json_cached(
        Path(MSST_ROOT) / "data" / "models_info.json", _MSST_INFO_CACHE
    )


def _detect_arch(config_path: str) -> Optional[str]:
    """Infer the architecture from a config file's model section.

    MSST's `get_model_from_config` needs the *architecture* (e.g.
    `mel_band_roformer`), not the storage folder (`vocal_models`).
    """
    try:
        import yaml

        with open(config_path, "r", encoding="utf-8") as fh:
            cfg = yaml.full_load(fh) or {}
        model = cfg.get("model") or {}
        if "freqs_per_bands" in model:
            return "bs_roformer"
        if "num_bands" in model:
            return "mel_band_roformer"
    except Exception as exc:  # pragma: no cover
        logger.debug("Arch detection failed for %s: %s", config_path, exc)
    return None


def _arch_from_catalog(model_id: str) -> Optional[str]:
    entry = _load_catalog().get(model_id, {})
    arch = (entry.get("arch") or "").lower()
    if "bs-roformer" in arch or "bs_roformer" in arch:
        return "bs_roformer"
    if "melband" in arch or "mel-band" in arch or "mel_band" in arch:
        return "mel_band_roformer"
    if arch == "mdx23c":
        return "mdx23c"
    if arch == "htdemucs":
        return "htdemucs"
    return None


def _resolve_msst_model(model_id: str) -> Optional[dict[str, str]]:
    """Map a catalog model id to (model_type, config_path, model_path).

    Resolution order:
      1. the managed local model store (downloaded on demand)
      2. an installed checkpoint registered in MSST's models_info.json
      3. the MSST pretrain/ convention
    """
    # 1. Managed store
    managed = manager.paths(model_id)
    if managed:
        arch = _detect_arch(managed["config_path"]) or _arch_from_catalog(model_id)
        if arch:
            return {
                "model_type": arch,
                "config_path": managed["config_path"],
                "model_path": managed["model_path"],
            }
        logger.warning(
            "Could not determine architecture for managed model %s", model_id
        )

    catalog = _load_catalog()
    entry = catalog.get(model_id)
    if not entry:
        return None

    checkpoint = entry.get("checkpoint")
    model_type = entry.get("model_type", "vocal_models")

    # Prefer an installed checkpoint registered in MSST's models_info.json
    info = _load_msst_models_info()
    if checkpoint and checkpoint in info:
        rec = info[checkpoint]
        target = rec.get("target_position", "")
        if target and os.path.exists(target):
            config_path = target.replace("pretrain", "configs") + ".yaml"
            return {
                # model_type = architecture (mel_band_roformer, bs_roformer…)
                "model_type": rec.get("model_type", model_type),
                "config_path": config_path,
                "model_path": target,
            }

    # Fall back to the pretrain dir convention
    if checkpoint:
        for sub in ("vocal_models", "multi_stem_models", "single_stem_models"):
            candidate = Path(MSST_ROOT) / "pretrain" / sub / checkpoint
            if candidate.exists():
                config_path = str(candidate).replace("pretrain", "configs") + ".yaml"
                return {
                    "model_type": model_type,
                    "config_path": config_path,
                    "model_path": str(candidate),
                }
    return None


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

class _MSSTBackend:
    """Wraps MSST-WebUI's MSSeparator (the verified local stack)."""

    name = "msst"

    def __init__(self) -> None:
        if MSST_ROOT not in sys.path:
            sys.path.insert(0, MSST_ROOT)
        from inference.msst_infer import MSSeparator  # type: ignore

        self._cls = MSSeparator

    def available_models(self) -> list[dict[str, Any]]:
        info = _load_msst_models_info()
        out = []
        for name, rec in info.items():
            if not rec.get("is_installed"):
                continue
            target = rec.get("target_position", "")
            if not target or not os.path.exists(target):
                continue
            out.append(
                {
                    "id": name,
                    "name": name,
                    "arch": "MSST",
                    "target": "dual",
                    "tags": ["installed"],
                    "sizeMB": round(rec.get("model_size", 0) / 1e6, 1),
                    "source": rec.get("link", ""),
                    # Licenses are declared upstream, not by this app. Anything
                    # not listed in the catalog's license map is UNSPECIFIED.
                    "license": "UNSPECIFIED",
                    "installed": True,
                    "checkpoint": name,
                    "model_type": rec.get("model_class", "vocal_models"),
                }
            )
        return out

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
        resolved = _resolve_msst_model(model_id)
        if resolved is None:
            raise RuntimeError(
                f"Model '{model_id}' is not installed. Add its checkpoint to "
                f"{MSST_ROOT}/pretrain and register it in models_info.json."
            )

        import librosa
        import soundfile as sf

        # On-demand model management: fetch + cache the checkpoint if the
        # local store doesn't have it yet. Repeat runs reuse the cache.
        rec = manager.get(model_id)
        if rec is not None and rec.downloadable and not manager.is_installed(model_id):
            progress(1, f"Downloading model {rec.name}")
            manager.ensure(
                model_id,
                on_progress=lambda pct, msg: progress(1 + pct * 0.03, msg),
            )

        # MSST's MSSeparator expects its custom logger (has console_handler).
        # get_logger() returns early without console_handler when the root
        # logger already has handlers (uvicorn does this), so ensure it exists.
        from utils.logger import get_logger

        msst_logger = get_logger()
        if not hasattr(msst_logger, "console_handler"):
            _ch = logging.StreamHandler()
            msst_logger.addHandler(_ch)
            msst_logger.console_handler = _ch

        sep = self._cls(
            model_type=resolved["model_type"],
            config_path=resolved["config_path"],
            model_path=resolved["model_path"],
            device="auto",
            device_ids=[0],
            output_format=output_format,
            use_tta=use_tta,
            store_dirs=output_dir,
            audio_params={
                "wav_bit_depth": "FLOAT",
                "flac_bit_depth": "PCM_24",
                "mp3_bit_rate": "320k",
            },
            logger=msst_logger,
        )

        sample_rate = getattr(sep.config.audio, "sample_rate", 44100)
        progress(5, "Loading audio")
        mix, sr = librosa.load(input_path, sr=sample_rate, mono=False)

        progress(10, "Running GPU inference")
        start = time.time()
        results = sep.separate(mix)
        elapsed = time.time() - start
        logger.info("Separation took %.1fs for %s", elapsed, model_id)

        stems: list[dict[str, Any]] = []
        os.makedirs(output_dir, exist_ok=True)
        total = len(results)
        for i, (instr, waveform) in enumerate(results.items()):
            if extract_instrumental and instr.lower() in ("vocals", "vocal"):
                continue
            fname = f"{Path(input_path).stem}_{instr}.{output_format}"
            out_path = os.path.join(output_dir, fname)
            sep.save_audio(waveform, sr, f"{Path(input_path).stem}_{instr}", output_dir)
            stems.append(
                {
                    "name": instr,
                    "url": f"/api/jobs/{Path(output_dir).name}/stems/{fname}",
                    "sizeBytes": os.path.getsize(out_path),
                    "format": output_format,
                }
            )
            progress(10 + int((i + 1) / total * 85), f"Saved {instr}")

        del mix, results
        gc.collect()
        progress(100, "Done")
        return stems


class _PymssBackend:
    """Drop-in fallback using pymss (audio-separator-compatible API)."""

    name = "pymss"

    def __init__(self) -> None:
        from pymss import Separator  # type: ignore

        self._cls = Separator

    def available_models(self) -> list[dict[str, Any]]:
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
        sep = self._cls(model_id=model_id, device="cuda")
        progress(10, "Running GPU inference")
        sep.separate(input_path, output_dir=output_dir, output_format=output_format)
        stems = []
        for f in sorted(Path(output_dir).iterdir()):
            if f.suffix.lstrip(".") == output_format:
                stems.append(
                    {
                        "name": f.stem.split("_")[-1],
                        "url": f"/api/jobs/{Path(output_dir).name}/stems/{f.name}",
                        "sizeBytes": f.stat().st_size,
                        "format": output_format,
                    }
                )
        progress(100, "Done")
        return stems


_backend: Optional[Any] = None


def get_backend() -> Any:
    global _backend
    if _backend is not None:
        return _backend
    if os.path.exists(Path(MSST_ROOT) / "inference" / "msst_infer.py"):
        try:
            _backend = _MSSTBackend()
            logger.info("Using MSST backend (%s)", MSST_ROOT)
            return _backend
        except Exception as exc:  # pragma: no cover
            logger.warning("MSST backend unavailable (%s); trying pymss", exc)
    try:
        _backend = _PymssBackend()
        logger.info("Using pymss backend")
        return _backend
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "No inference backend available. Install MSST-WebUI or pymss."
        ) from exc


def list_models() -> list[dict[str, Any]]:
    """Catalog + live install state from the ModelManager, plus any extra
    checkpoints discovered in the MSST pretrain directory."""
    merged = manager.list()
    # A model is usable if it's in the managed store OR already present in the
    # MSST checkout. Don't offer to re-download something we can already load.
    for m in merged:
        if not m.get("installed"):
            try:
                from_msst = _resolve_msst_model(m["id"])
            except Exception:  # pragma: no cover
                from_msst = None
            if from_msst:
                m["installed"] = True
                m["installedVia"] = "msst"
                path = from_msst.get("model_path", "")
                if path and os.path.exists(path):
                    m["sizeBytes"] = os.path.getsize(path)
                    m["sizeMB"] = round(m["sizeBytes"] / 1e6, 1)
        else:
            m["installedVia"] = "store"
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