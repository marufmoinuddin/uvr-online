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
import sys
import tempfile
import time

import yaml
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from model_manager import manager, resolve_registry_dir as _resolve_registry_dir

logger = logging.getLogger("uvr.inference")

OUTPUT_ROOT = Path(os.environ.get("OUTPUT_ROOT", "./output"))
MODEL_CATALOG_PATH = Path(os.environ.get("MODEL_CATALOG", "./models.json"))

# audio-separator raises FileNotFoundError if its model directory does not
# already exist, and the model volume is bind-mounted over anything the image
# created at build time — so make sure it is there at import.
_registry_dir = os.environ.get("AUDIO_SEPARATOR_MODEL_DIR")
if _registry_dir:
    try:
        Path(_registry_dir).mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover
        logging.getLogger("uvr.inference").warning(
            "Could not create AUDIO_SEPARATOR_MODEL_DIR %s: %s", _registry_dir, exc
        )



def _patch_melband_mlp_expansion() -> bool:
    """Forward `mlp_expansion_factor` into audio-separator's MelBand mask estimator.

    audio-separator (verified on 0.47.0) drops this parameter on the MelBand
    path only. The chain is:

      * `roformer_loader._create_mel_band_roformer` **does** pass
        `mlp_expansion_factor` (default 4) into `MelBandRoformer`
      * `MelBandRoformer.__init__` accepts and stores it
      * `mel_band_roformer.py:331` then builds
        `MaskEstimator(dim=..., dim_inputs=..., depth=mask_estimator_depth)`
        **without forwarding it**, so `MaskEstimator` falls back to its own
        default of 4

    The sibling `bs_roformer.py:423` *does* forward it, which is why
    BS-RoFormer checkpoints trained with factor 1 load and MelBand ones do not.

    Measured on `melband_roformer_guitar_becruily.ckpt` (author config says
    `mlp_expansion_factor: 1`): checkpoint mask-MLP hidden = 256, built = 1024
    (= 256 x 4), and `load_state_dict(strict=True)` raises `size mismatch`.
    With this patch the strict load passes with 0 missing / 0 unexpected /
    0 mismatched keys.

    Patched at runtime rather than by editing site-packages, which a `uv sync`
    would silently revert. Inference is serial (one job at a time), so the
    module-level hand-off is not racy.

    Returns True if the patch is active.
    """
    try:
        from audio_separator.separator.uvr_lib_v5.roformer import (
            mel_band_roformer as mbr,
        )
    except Exception as exc:  # pragma: no cover - dependency layout change
        logger.debug("MelBand mlp_expansion_factor patch unavailable: %s", exc)
        return False

    if getattr(mbr, "_uvr_mlp_forwarding", False):
        return True

    original_mask_init = mbr.MaskEstimator.__init__
    original_model_init = mbr.MelBandRoformer.__init__

    def mask_init(self, dim, dim_inputs, depth, mlp_expansion_factor=4):
        forced = getattr(mbr, "_uvr_mlp_expansion_factor", None)
        if forced is not None:
            mlp_expansion_factor = forced
        original_mask_init(self, dim, dim_inputs, depth, mlp_expansion_factor)

    def model_init(self, *args, **kwargs):
        mbr._uvr_mlp_expansion_factor = kwargs.get("mlp_expansion_factor")
        try:
            original_model_init(self, *args, **kwargs)
        finally:
            mbr._uvr_mlp_expansion_factor = None

    mbr.MaskEstimator.__init__ = mask_init
    mbr.MelBandRoformer.__init__ = model_init
    mbr._uvr_mlp_forwarding = True
    logger.info("Patched MelBand mask-estimator mlp_expansion_factor forwarding")
    return True


# The resolver lives in model_manager so install-state reporting and the
# loader always agree on where the registry cache lives; re-exported here
# because call sites (and scripts/probe-registry-model.py) import it from
# this module.
resolve_registry_dir = _resolve_registry_dir

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


# Stem names reach us from two different places and disagree on spelling: the
# vendored MSST path writes whatever the model config calls an instrument
# ("vocals", "instrument"), while audio-separator writes the parenthesised part
# of its output filename ("Vocals", "Instrumental"). The UI then shows two
# spellings of the same stem depending on which backend ran.
#
# Canonicalising at this boundary means the rest of the app only ever sees one
# spelling, and a model config that names an instrument differently cannot leak
# an odd label into the player or the download filename.
_STEM_SYNONYMS = {
    "vocal": "Vocals",
    "vocals": "Vocals",
    "lead_vocals": "Vocals",
    "lead vocals": "Vocals",
    "backing_vocals": "Vocals",
    "backing vocals": "Vocals",
    "bvocals": "Vocals",
    "vocalmain": "Vocals",
    "instrument": "Instrumental",
    "instrumental": "Instrumental",
    "accompaniment": "Instrumental",
    "no_vocals": "Instrumental",
    "other": "Other",
    "others": "Other",
    "drum": "Drums",
    "drums": "Drums",
    "bass": "Bass",
    "bassline": "Bass",
    # Drum-family stems written by MDX DrumSep. The author abbreviates the
    # hi-hat, so normalise it to the same label the Instrument Extractor offers.
    "hh": "Hi-Hat",
    "hihat": "Hi-Hat",
    "hi_hat": "Hi-Hat",
    "hi-hat": "Hi-Hat",
    "kick": "Kick",
    "snare": "Snare",
    "toms": "Toms",
    "tom": "Toms",
    "ride": "Ride",
    "crash": "Crash",
}


def canonical_stem_name(raw: str) -> str:
    """Normalise a stem label to a single, consistent spelling.

    Unknown names are title-cased rather than dropped, so a new architecture
    still produces a readable label instead of an empty one.
    """
    name = (raw or "").strip()
    if not name:
        return "Stem"
    key = name.lower().replace("-", "_")
    if key in _STEM_SYNONYMS:
        return _STEM_SYNONYMS[key]
    spaced = name.replace("_", " ").strip()
    return spaced[:1].upper() + spaced[1:] if spaced else "Stem"


def finalise_stems(stems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Canonicalise stem names and guarantee they are unique within a job.

    Two backends can canonicalise different sources onto the same label (e.g. a
    config naming both "instrument" and "Instrumental"). Duplicate names would
    break React keys in the player and collide in a download bundle, so a
    counter suffix is added.
    """
    seen: dict[str, int] = {}
    out: list[dict[str, Any]] = []
    for stem in stems:
        base = canonical_stem_name(stem.get("name", ""))
        n = seen.get(base, 0) + 1
        seen[base] = n
        name = base if n == 1 else f"{base} {n}"
        out.append({**stem, "name": name})
    return out


def _local_model_type(arch: Optional[str]) -> str:
    """Map a catalog architecture to an audio-separator model type.

    Our catalog carries UVR-style architecture names; the library groups its
    loaders by model type. BS-RoFormer / Mel-Band RoFormer / MDX23C all load
    through MDXCSeparator (which is what its own registry uses for RoFormers).
    """
    a = (arch or "").lower()
    if "demucs" in a:
        return "Demucs"
    if a == "vr" or "vr_" in a:
        return "VR"
    return "MDXC"


# ---------------------------------------------------------------------------
# Bundled MSST inference
#
# audio-separator reimplements BS-RoFormer and so cannot load checkpoints that
# use extra layers — the "HyperACE" variants add FNO/hypergraph modules and
# fail with a state_dict mismatch. Rather than lose those models, MSST-WebUI's
# own implementation is vendored under `vendor/msst`, and used for any model
# whose config declares them. Keeping MSST's code and weights together is what
# makes these loadable without depending on an external checkout.
# ---------------------------------------------------------------------------

_VENDOR_ROOT = Path(__file__).resolve().parent / "vendor" / "msst"


def _load_msst_modules() -> tuple[Any, Any]:
    """Import the vendored MSST helpers, adding them to sys.path once."""
    vendor = str(_VENDOR_ROOT)
    if vendor not in sys.path:
        sys.path.insert(0, vendor)
    from infer import demix, get_model_from_config  # type: ignore

    return demix, get_model_from_config


def _config_uses_msst(config_path: str) -> Optional[str]:
    """Return MSST's model_type for this config, or None if it is a plain model.

    NOTE: must use FullLoader. These configs contain `!!python/tuple`
    (for freqs_per_bands), which yaml.safe_load *raises* on — and a silent
    `except` would then make every HyperACE model look like a plain one.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            raw = yaml.load(fh, Loader=yaml.FullLoader) or {}
    except Exception as exc:
        logger.debug("Could not read config %s: %s", config_path, exc)
        return None
    model = raw.get("model") or {}
    # Explicit flag, when a config bothers to declare it.
    if model.get("use_mask_estimator_hyper_ace") or "hyperace_version" in model:
        return "mel_band_roformer" if "num_bands" in model else "bs_roformer"
    return None


def _checkpoint_needs_hyperace(model_path: str) -> bool:
    """Detect HyperACE from the weights, not the config.

    The published HyperACE configs do NOT declare it — `config.yaml` is a plain
    BS-RoFormer config — but the checkpoint contains `...segm.hyperace.*` keys
    that a plain BS-RoFormer has no module for. So the weights are the only
    reliable signal, and it is what actually decides whether the state dict
    will load.
    """
    try:
        import torch

        sd = torch.load(model_path, map_location="cpu", weights_only=False)
    except Exception as exc:
        logger.debug("Could not probe %s for HyperACE: %s", model_path, exc)
        return False
    for key in ("state", "state_dict"):
        if isinstance(sd, dict) and key in sd:
            sd = sd[key]
    if not isinstance(sd, dict):
        return False
    return any("hyperace" in str(k).lower() for k in sd.keys())


def _separate_with_msst(
    model_id: str,
    config_path: str,
    model_path: str,
    input_path: str,
    output_dir: str,
    output_format: str,
    extract_instrumental: bool,
    progress: ProgressFn,
) -> list[dict[str, Any]]:
    """Run separation through the vendored MSST implementation.

    Mirrors MSST-WebUI's MSSeparator.separate(): normalise if configured,
    demix, then derive the complementary stem from the original mix when the
    model targets a single instrument.
    """
    import librosa
    import numpy as np
    import soundfile as sf
    import torch

    model_type = _config_uses_msst(config_path)
    needs_hyperace = _checkpoint_needs_hyperace(model_path)
    if model_type is None and not needs_hyperace:  # pragma: no cover
        raise RuntimeError("Config does not describe a supported architecture")

    demix, _get_model_from_config = _load_msst_modules()

    progress(3, "Loading model")

    # Build the architecture ourselves rather than via get_model_from_config:
    # the HyperACE flags have to be injected, because the published configs do
    # not declare them (see _checkpoint_needs_hyperace).
    with open(config_path, "r", encoding="utf-8") as fh:
        raw_cfg = yaml.load(fh, Loader=yaml.FullLoader) or {}
    model_cfg = dict(raw_cfg.get("model") or {})

    if needs_hyperace:
        model_cfg["use_mask_estimator_hyper_ace"] = True
        model_cfg.setdefault("hyperace_version", 2)
        logger.info("HyperACE layers detected in %s — enabling them", model_id)

    from ml_collections import ConfigDict

    if "num_bands" in model_cfg:
        from modules.bs_roformer import MelBandRoformer as _Arch

        model_type = model_type or "mel_band_roformer"
    else:
        from modules.bs_roformer import BSRoformer as _Arch

        model_type = model_type or "bs_roformer"

    model = _Arch(**model_cfg)
    config = ConfigDict(raw_cfg)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    state = torch.load(model_path, map_location=device, weights_only=False)
    for key in ("state", "state_dict"):
        if isinstance(state, dict) and key in state:
            state = state[key]
    model.load_state_dict(state)
    model = model.to(device).eval()

    is_stereo = True
    if model_type in ("bs_roformer", "mel_band_roformer"):
        is_stereo = bool((config.model or {}).get("stereo", True))

    progress(10, "Loading audio")
    mix, _sr = librosa.load(input_path, sr=config.audio.sample_rate, mono=not is_stereo)
    if is_stereo and mix.ndim == 1:
        mix = np.stack([mix, mix], axis=0)
    elif not is_stereo and mix.ndim != 1:
        mix = np.mean(mix, axis=0)

    mix_orig = mix.copy()
    norm_params = None
    if (config.inference or {}).get("normalize"):
        mean, std = mix.mean(), mix.std()
        mix = (mix - mean) / (std + 1e-8)
        norm_params = {"mean": mean, "std": std}

    progress(20, "Running GPU inference")
    started = time.time()
    with torch.no_grad():
        waveforms = demix(config, model, mix, device, model_type=model_type)
    logger.info("MSST separation took %.1fs for %s", time.time() - started, model_id)

    target = config.training.target_instrument
    instruments = [target] if target else list(config.training.instruments)

    os.makedirs(output_dir, exist_ok=True)
    stems: list[dict[str, Any]] = []
    total = max(len(instruments), 1)

    def _write(name: str, audio: "np.ndarray") -> None:
        if norm_params is not None:
            audio = audio * norm_params["std"] + norm_params["mean"]
        fname = f"{Path(input_path).stem}_{name}.{output_format}"
        sf.write(
            os.path.join(output_dir, fname),
            audio,
            config.audio.sample_rate,
            subtype={"wav": "PCM_16", "flac": "PCM_16", "mp3": "PCM_16"}.get(output_format),
        )
        stems.append(
            {
                "name": name,
                "url": f"/api/jobs/{Path(output_dir).name}/stems/{fname}",
                "sizeBytes": os.path.getsize(os.path.join(output_dir, fname)),
                "format": output_format,
            }
        )

    for i, instr in enumerate(instruments):
        if extract_instrumental and str(instr).lower().startswith("vocal"):
            continue
        _write(str(instr), waveforms[instr].T)
        progress(20 + int((i + 1) / total * 70), f"Saved {instr}")

    # Single-target models: the complement is the original mix minus the target.
    if target:
        others = [i for i in config.training.instruments if i != target]
        if others and not extract_instrumental:
            _write(str(others[0]), (mix_orig - waveforms[target]).T)

    del model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    progress(100, "Done")
    return finalise_stems(stems)


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

        # Refuse models the catalog has flagged as unrunnable by this backend.
        # Catching it here means the user gets an immediate, explanatory error
        # instead of downloading hundreds of MB and then failing to load.
        if rec is not None and getattr(rec, "unsupported", None):
            raise RuntimeError(
                f"'{rec.name}' cannot be used with this backend. {rec.unsupported}"
            )

        if rec is not None and rec.downloadable and not manager.is_installed(model_id):
            progress(1, f"Downloading model {rec.name}")
            manager.ensure(
                model_id,
                on_progress=lambda pct, msg: progress(1 + pct * 0.03, msg),
            )

        paths = manager.paths(model_id)

        # Checkpoints audio-separator cannot load (the HyperACE variants) run
        # on the vendored MSST implementation instead. Decided up-front from the
        # checkpoint itself, because audio-separator calls sys.exit() on a bad
        # load rather than raising, so a try/except fallback is not an option.
        if paths and (
            _checkpoint_needs_hyperace(paths["model_path"])
            or _config_uses_msst(paths["config_path"])
        ):
            progress(2, "Loading model")
            return _separate_with_msst(
                model_id,
                paths["config_path"],
                paths["model_path"],
                input_path,
                output_dir,
                output_format,
                extract_instrumental,
                progress,
            )

        os.makedirs(output_dir, exist_ok=True)
        sep_kwargs: dict[str, Any] = {
            "output_dir": output_dir,
            "output_format": output_format.upper(),
            "use_autocast": True,
        }

        progress(5, "Loading model")

        if paths:
            # A checkpoint from our managed store. These are NOT in
            # audio-separator's curated registry, and `load_model()` calls
            # `download_model_files()` first, which only searches that registry
            # and then raises — even though the file is sitting right there in
            # `model_file_dir`.
            #
            # So bypass just that lookup, supplying the values it would have
            # computed, and let the library's own loading logic run unchanged.
            # `load_model_data_from_yaml` accepts our RoFormer `config.yaml`
            # as-is and flags it as a RoFormer, so no schema translation is
            # needed.
            ckpt = Path(paths["model_path"])
            _ensure_config_aliases(ckpt.parent)
            rec = manager.get(model_id)
            model_type = _local_model_type(getattr(rec, "arch", None))

            sep = self._cls(model_file_dir=str(ckpt.parent), **sep_kwargs)
            original = sep.download_model_files
            sep.download_model_files = lambda fn: (  # type: ignore[assignment]
                ckpt.name,
                model_type,
                model_id,
                str(ckpt),
                ckpt.with_suffix(".yaml").name,
            )
            try:
                sep.load_model(model_filename=ckpt.name)
            finally:
                sep.download_model_files = original  # type: ignore[assignment]
        else:
            # Nothing in our local store. Use the equivalent model from
            # audio-separator's own registry when the catalog names one — the
            # library then downloads the weights and its matching config
            # itself. Otherwise treat the id as a registry filename directly.
            #
            # The registry cache defaults to /tmp, which is wiped on restart,
            # so point it at a persistent location. Resolved through
            # resolve_registry_dir() because <MODEL_STORE>/.registry can be
            # left root-owned by an earlier Docker run, which made every
            # registry-backed model fail locally with "Permission denied".
            # This is passed per-call rather than via
            # AUDIO_SEPARATOR_MODEL_DIR, because that env var overrides
            # model_file_dir globally and would clobber the local-store path.
            registry_dir = resolve_registry_dir()
            registry_name = getattr(rec, "registry", None) or model_id
            sep = self._cls(model_file_dir=str(registry_dir), **sep_kwargs)
            sep.load_model(model_filename=registry_name)

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

        # Release the checkpoint and return its VRAM. Without this the next job
        # starts with ~1.2 GB still held, needs more than the card has left, and
        # dies with a native SIGSEGV that takes the whole worker down.
        #
        # torch is imported function-locally throughout this module, so it is
        # NOT in scope here — importing it locally is required, not stylistic.
        import torch

        sep.model_instance = None
        del sep
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        progress(100, "Done")
        return finalise_stems(stems)


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


def select_instrument(
    stems: list[dict[str, Any]], target: str, model_id: str
) -> list[dict[str, Any]]:
    """Reduce a full stem set to just the requested instrument.

    Returns a ONE-ELEMENT list so every consumer (player, bundle, history) keeps
    working exactly as it does for a repair job.

    Raises rather than substituting anything: silently returning `Other` or the
    first output would hand the user a file of the wrong sound while reporting
    success — the exact failure mode this project exists to eliminate.
    """
    # Canonicalise BOTH sides rather than comparing raw strings. The stem a
    # model writes and the label a user picks often differ in more than case —
    # MDX DrumSep writes "hh" while the picker offers "Hi-Hat" — and
    # `_STEM_SYNONYMS` already folds those together.
    if not (target or "").strip():
        return stems
    want = canonical_stem_name(target).lower()

    # Compare through the canonical names so "guitar" matches "Guitar" and a
    # model's own spelling (e.g. "piano") is not required.
    for stem in stems:
        name = canonical_stem_name(stem.get("name", ""))
        if name.lower() == want:
            return [{**stem, "name": name}]

    available = ", ".join(sorted({canonical_stem_name(s.get("name", "")) for s in stems}))
    raise ValueError(
        f"Model '{model_id}' did not produce a '{target}' stem. "
        f"Available: {available or 'none'}. "
        "Pick a model that separates that instrument, or choose another target."
    )


def separate_file(
    model_id: str,
    input_path: str,
    output_dir: str,
    output_format: str = "mp3",
    use_tta: bool = False,
    extract_instrumental: bool = False,
    progress: Optional[ProgressFn] = None,
    extract_target: Optional[str] = None,
) -> list[dict[str, Any]]:
    progress = progress or (lambda p, s: None)
    # Apply before any model is constructed. Idempotent, and harmless for
    # checkpoints that were trained with the default factor of 4.
    _patch_melband_mlp_expansion()
    backend = get_backend()
    stems = backend.separate(
        model_id,
        input_path,
        output_dir,
        output_format,
        use_tta,
        extract_instrumental,
        progress,
    )
    if extract_target:
        stems = select_instrument(stems, extract_target, model_id)
        progress(95, f"Selected {canonical_stem_name(stems[0]['name'])}")
    return stems