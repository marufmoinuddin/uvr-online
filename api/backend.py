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
import threading
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


# ---------------------------------------------------------------------------
# Device selection
#
# ONE place decides where separation runs. The worker, the health endpoint,
# the queue and the model guard all ask here, so they cannot disagree about
# which device is in use — a worker that thinks it is on the CPU while the
# queue labels the job "GPU" is exactly the kind of lie this project exists
# to eliminate.
#
#   UVR_DEVICE=auto   CUDA when a usable GPU is present, otherwise CPU
#   UVR_DEVICE=cuda   require CUDA; refuse to start if there is none
#   UVR_DEVICE=cpu    never touch the GPU
#
# `cuda` deliberately FAILS on a machine without a GPU instead of falling back
# silently: a silent fallback turns "I asked for the GPU" into a CPU job that
# runs for an hour, and the user only finds out from the elapsed time.
# ---------------------------------------------------------------------------

DEVICE_ENV = "UVR_DEVICE"
DEVICE_THREADS_ENV = "UVR_CPU_THREADS"

# Set to "1" to let the measurement tool run the models the worker refuses in
# CPU mode. See assert_runnable(). Never set in a deployment.
ALLOW_BLOCKED_ENV = "UVR_ALLOW_BLOCKED_MODELS"

# The CPU profile. A separate block of settings, not a set of inline
# conditionals, so tuning the GPU path can never quietly change the CPU one
# (and vice versa).
#
#   batch_size   chunks per forward pass. Batching only pays off when the
#                maths is bandwidth-bound; on CPU it mostly adds memory
#                pressure and lengthens every progress tick.
#   num_overlap  overlap factor. The vendored demix walks the clip in steps of
#                chunk_size / num_overlap, so 4 processes the audio 4x over.
#                Halving it halves the work, at the cost of seam artefacts.
CPU_PROFILE: dict[str, Any] = {
    "batch_size": 1,
    "num_overlap": 2,
}


# CPU-mode limits. A CPU run is orders of magnitude slower than a GPU run, so
# an unbounded job is not merely slow — it blocks the single-threaded queue for
# hours and every other user waits behind it. These bounds are enforced at
# submit time (so the user is told immediately) and at run time (so a job
# that slipped through still ends).
CPU_MAX_SECONDS_ENV = "UVR_CPU_MAX_SECONDS"
CPU_MAX_BYTES_ENV = "UVR_CPU_MAX_BYTES"
CPU_JOB_TIMEOUT_ENV = "UVR_CPU_JOB_TIMEOUT"
GPU_JOB_TIMEOUT_ENV = "UVR_GPU_JOB_TIMEOUT"

DEFAULT_CPU_MAX_SECONDS = 120
DEFAULT_CPU_MAX_BYTES = 64 * 1024 * 1024
DEFAULT_CPU_JOB_TIMEOUT = 1800
DEFAULT_GPU_JOB_TIMEOUT = 3600


def _int_env(name: str, default: int) -> int:
    """Read a positive integer from the environment, falling back to `default`."""
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        logger.warning("Ignoring invalid %s=%r (expected a positive integer)", name, raw)
        return default
    return value if value > 0 else default


def cpu_max_seconds() -> int:
    """Longest clip CPU mode accepts, in seconds."""
    return _int_env(CPU_MAX_SECONDS_ENV, DEFAULT_CPU_MAX_SECONDS)


def cpu_max_bytes() -> int:
    """Largest upload CPU mode accepts, in bytes."""
    return _int_env(CPU_MAX_BYTES_ENV, DEFAULT_CPU_MAX_BYTES)


def job_timeout(device: str) -> int:
    """Wall-clock ceiling for one job, in seconds.

    The separation runs in a child process, so this is a real ceiling: the
    process is killed when it is reached.
    """
    if device == "cpu":
        return _int_env(CPU_JOB_TIMEOUT_ENV, DEFAULT_CPU_JOB_TIMEOUT)
    return _int_env(GPU_JOB_TIMEOUT_ENV, DEFAULT_GPU_JOB_TIMEOUT)


def cpu_limits() -> dict[str, Any]:
    """The CPU-mode bounds, published by the health endpoint for the UI."""
    return {
        "maxSeconds": cpu_max_seconds(),
        "maxBytes": cpu_max_bytes(),
        "timeoutSeconds": _int_env(CPU_JOB_TIMEOUT_ENV, DEFAULT_CPU_JOB_TIMEOUT),
    }


def _cgroup_cpu_limit() -> Optional[int]:
    """How many CPUs the cgroup actually grants, or None when unlimited.

    A container with a CPU quota still reports the HOST's core count to
    `os.cpu_count()`, so torch would start one thread per host core and every
    one of them would fight over the same quota — the classic CPU
    oversubscription that makes a "slow CPU" run absurdly slow.
    """
    # cgroup v2: "max 100000" when unlimited, "<quota> <period>" otherwise.
    try:
        raw = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if raw and raw[0] != "max":
            quota, period = int(raw[0]), int(raw[1])
            if quota > 0 and period > 0:
                return max(1, -(-quota // period))  # ceil division
    except (OSError, ValueError, IndexError):
        pass
    # cgroup v1
    try:
        quota = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text().strip())
        period = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text().strip())
        if quota > 0 and period > 0:
            return max(1, -(-quota // period))
    except (OSError, ValueError):
        pass
    return None


def effective_cpu_threads() -> int:
    """Threads CPU inference may actually use.

    The smallest of the CPU affinity mask, the cgroup quota and the host core
    count — that is what this process can really get. `UVR_CPU_THREADS`
    overrides it when a user knows better.
    """
    override = os.environ.get(DEVICE_THREADS_ENV)
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            logger.warning(
                "Ignoring invalid %s=%r (expected a positive integer)",
                DEVICE_THREADS_ENV,
                override,
            )
    try:
        affinity = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):  # pragma: no cover - non-Linux
        affinity = os.cpu_count() or 1
    limits = [n for n in (affinity, _cgroup_cpu_limit(), os.cpu_count()) if n]
    return max(1, min(limits) if limits else 1)


def resolve_device() -> str:
    """The device inference will run on: "cuda" or "cpu".

    Raises when the environment asks for something impossible (CUDA on a
    machine without a GPU, or a misspelled value) rather than guessing.
    """
    pref = (os.environ.get(DEVICE_ENV) or "auto").strip().lower()
    if pref not in ("auto", "cuda", "cpu"):
        raise RuntimeError(
            f"Invalid {DEVICE_ENV}={pref!r}. Use 'auto', 'cuda' or 'cpu'."
        )
    if pref == "cuda":
        if not _using_cuda():
            raise RuntimeError(
                f"{DEVICE_ENV}=cuda was requested but no CUDA device is available. "
                "Set UVR_DEVICE=auto to fall back to the CPU automatically."
            )
        return "cuda"
    if pref == "cpu":
        return "cpu"
    return "cuda" if _using_cuda() else "cpu"


def configure_runtime(device: Optional[str] = None) -> dict[str, Any]:
    """Prepare torch for the chosen device and report what was applied.

    On CPU this turns off every fast-but-approximate path: autocast (float16
    matmuls), TF32 and reduced-precision matmul. CPU inference is already the
    slow path, so it should at least be the *correct* one — and float16 on CPU
    is not merely slower, many kernels are simply missing and fall back to
    something worse.

    Returns a small dict describing the resulting configuration, which the
    health endpoint publishes so the UI can show the real numbers.
    """
    import torch

    device = device or resolve_device()
    info: dict[str, Any] = {"device": device}

    if device == "cpu":
        limit = effective_cpu_threads()
        # Only ever REDUCE the thread count. Torch's own default is already a
        # sensible choice; raising it above the cgroup quota is exactly the
        # oversubscription this function exists to prevent.
        if torch.get_num_threads() > limit:
            torch.set_num_threads(limit)
        info["threads"] = torch.get_num_threads()
        info["threadsLimit"] = limit
        torch.set_float32_matmul_precision("highest")
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        info["autocast"] = False
        info["tf32"] = False
    else:
        info["threads"] = torch.get_num_threads()
        info["threadsLimit"] = effective_cpu_threads()
        info["autocast"] = True
        info["tf32"] = True
    return info


def cpu_ok(model_id: str) -> bool:
    """Can this model run on the CPU at all?

    The catalogue decides (`cpuOk`); this only reads it. The answer comes from
    measurement, not from the architecture name — a RoFormer is not
    automatically too slow, and a Demucs is not automatically fast.
    """
    rec = manager.get(model_id)
    if rec is None:
        return False
    return bool(getattr(rec, "cpu_ok", False))


def assert_runnable(model_id: str, device: str, *, allow_cpu_blocked: bool = False) -> None:
    """Refuse a model the chosen device cannot run, with a usable reason.

    Called before any weight is downloaded, so the user gets an immediate
    explanation instead of a long wait followed by a failure.

    `allow_cpu_blocked` exempts the CPU-speed restriction (but not the
    `unsupported` one): the Audio Repair pipeline runs a neural model as one
    light pass wrapped in DSP, and is documented as CPU-usable. Its models are
    deliberately NOT held to the separation-mode speed cutoff.
    """
    rec = manager.get(model_id)
    if rec is None:
        raise RuntimeError(f"Unknown model '{model_id}'.")
    if rec.unsupported:
        raise RuntimeError(f"'{rec.name}' cannot be used: {rec.unsupported}")
    if device == "cpu" and not rec.cpu_ok and not allow_cpu_blocked:
        # Escape hatch for the MEASUREMENT tool only. scripts/benchmark-cpu.py
        # has to be able to time the very models the worker refuses — without
        # that, the refusal has no evidence behind it. Never set this in a
        # deployment.
        if os.environ.get(ALLOW_BLOCKED_ENV) == "1":
            logger.warning(
                "Allowing CPU-blocked model %s (measurement mode)", model_id
            )
            return
        raise RuntimeError(
            f"'{rec.name}' is not supported in CPU mode. It is one of the heavy "
            "models that would take hours on a CPU. Pick a lighter model "
            "(the CPU-compatible ones are marked in the picker), or run the "
            "worker with UVR_DEVICE=cuda on a machine with a GPU."
        )


def _cpu_separator_params() -> dict[str, Any]:
    """Per-architecture parameter overrides for CPU mode.

    audio-separator takes one dict per architecture family (`mdx_params`,
    `vr_params`, `demucs_params`, `mdxc_params`). The names below are the ones
    the library actually reads (verified against audio-separator 0.47) — an
    unknown key is silently ignored, so a typo here would cost an order of
    magnitude in time and say nothing.

    * `overlap` / `num_overlap` — the chunk walk is `step = chunk / overlap`,
      so a HIGHER overlap means MORE chunks and more work. Halving it halves
      the compute, at the cost of seam artefacts.
    * `shifts` and `enable_tta` — each multiplies the number of forward
      passes. On an already-slow CPU they are the first things to go.
    * `batch_size` — batching only pays off when the maths is bandwidth-bound;
      on CPU it mostly adds memory pressure and lengthens every progress tick.

    Any key left out falls back to the library's own default, so the dicts
    below are complete on their own.
    """
    return {
        "mdx_params": {
            "hop_length": 1024,
            "segment_size": 256,
            "overlap": 0.1,
            "batch_size": 1,
            "enable_denoise": False,
        },
        "vr_params": {
            "batch_size": 1,
            "window_size": 512,
            "aggression": 5,
            "enable_tta": False,
            "enable_post_process": False,
            "post_process_threshold": 0.2,
            "high_end_process": False,
        },
        "demucs_params": {
            "segment_size": "Default",
            "shifts": 0,
            "overlap": 0.1,
            "segments_enabled": True,
        },
        "mdxc_params": {
            "segment_size": 256,
            "override_model_segment_size": False,
            "batch_size": 1,
            "overlap": 2,
            "pitch_shift": 0,
        },
    }


def _supported_kwargs(sep_cls: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Drop kwargs the installed audio-separator does not accept.

    The library's constructor signature has changed across releases (the
    per-architecture `*_params` dicts are relatively recent). Passing an
    unknown keyword is a hard TypeError, which would take down a CPU run that
    is otherwise fine, so the constructor is inspected first.
    """
    import inspect

    try:
        params = inspect.signature(sep_cls.__init__).parameters
    except (TypeError, ValueError):  # pragma: no cover - exotic callables
        return kwargs
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return kwargs
    dropped = sorted(set(kwargs) - set(params))
    if dropped:
        logger.debug("audio-separator does not accept %s", ", ".join(dropped))
    return {k: v for k, v in kwargs.items() if k in params}


def _pin_device(sep: Any, device: str) -> None:
    """Pin an audio-separator instance to `device`.

    The library chooses CUDA whenever it is available, which is wrong when the
    operator asked for CPU mode on a machine that happens to have a GPU — the
    job would silently run on the card and the CPU thread budget would go
    unused.
    """
    import torch

    target = torch.device(device)
    for attr in ("torch_device", "device"):
        if not hasattr(sep, attr):
            continue
        try:
            setattr(sep, attr, target)
        except Exception:  # pragma: no cover - read-only attribute
            logger.debug("Could not pin Separator.%s", attr, exc_info=True)

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


def _using_cuda() -> bool:
    """Is a CUDA device actually available right now?

    A helper rather than a bare `torch.cuda.is_available()` because torch is
    imported function-locally throughout this module (to keep import cost off
    the DSP-only repair path), so a bare reference at module scope raises
    `NameError: cannot access local variable 'torch'`. Every device decision
    goes through here so there is one answer, not several.
    """
    import torch

    try:
        return bool(torch.cuda.is_available())
    except Exception:  # pragma: no cover - driver/runtime mismatch
        return False


def _install_progress_hook(report: Callable[[float], None]) -> Optional[Callable[[], None]]:
    """Make `audio-separator`'s chunk loops report real progress.

    The library has no progress callback of its own — it drives `tqdm`
    directly, and the only progress the worker could report was a fake 10%
    jump at the start of inference. The bar then sat still for the whole run,
    which on a CPU reads as a hung job, and the ETA derived from it was
    meaningless.

    Hooking `tqdm` is the only place the library exposes the chunk loop, so
    that is where the progress comes from. Two shapes are patched:

    * the architecture modules, which do `from tqdm import tqdm` and call the
      class directly;
    * the vendored Demucs helpers, which do `import tqdm` and call
      `tqdm.tqdm(...)`.

    The second one patches a shared module, so a **restore callable** is
    returned and the patch is undone as soon as the run is over. Inference is
    serial (one job at a time, in its own process), so there is nothing to
    race with either way.

    Returns the restore callable, or None if nothing could be hooked.
    """
    import importlib

    try:
        from tqdm import tqdm as real_tqdm
    except ImportError:  # pragma: no cover - tqdm is an audio-separator dep
        return None

    class _ReportingTqdm(real_tqdm):  # type: ignore[misc, valid-type]
        """tqdm that reports each chunk as it completes."""

        def __init__(self, iterable=None, *args, **kwargs):
            total = kwargs.get("total")
            if total is None:
                try:
                    total = len(iterable)  # type: ignore[arg-type]
                except TypeError:
                    total = None
            self._uvr_total = total
            self._uvr_done = 0
            super().__init__(iterable, *args, **kwargs)

        def update(self, n=1):
            self._uvr_done += n
            if self._uvr_total:
                try:
                    report(min(1.0, self._uvr_done / self._uvr_total))
                except Exception:  # pragma: no cover - never break inference
                    pass
            return super().update(n)

    restores: list[Callable[[], None]] = []

    for module in ("mdxc_separator", "vr_separator", "mdx_separator"):
        try:
            mod = importlib.import_module(
                f"audio_separator.separator.architectures.{module}"
            )
        except Exception:  # pragma: no cover - layout change
            continue
        if getattr(mod, "tqdm", None) is real_tqdm:
            mod.tqdm = _ReportingTqdm
            restores.append(lambda m=mod: setattr(m, "tqdm", real_tqdm))

    # The vendored Demucs helpers import the tqdm MODULE, so the class has to
    # be replaced inside it. That is a shared object, hence the restore.
    try:
        import tqdm as tqdm_module

        if getattr(tqdm_module, "tqdm", None) is real_tqdm:
            tqdm_module.tqdm = _ReportingTqdm
            restores.append(lambda: setattr(tqdm_module, "tqdm", real_tqdm))
    except Exception:  # pragma: no cover
        pass

    if not restores:
        return None

    def restore() -> None:
        for fn in restores:
            try:
                fn()
            except Exception:  # pragma: no cover
                pass

    return restore


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

    device = resolve_device()
    configure_runtime(device)

    # CPU profile. Applied ONLY on CPU, so the GPU quality settings stay
    # exactly as the model's config declares them.
    if device == "cpu":
        inference = getattr(config, "inference", None)
        if inference is not None:
            for key, value in CPU_PROFILE.items():
                if getattr(inference, key, None) is not None:
                    inference[key] = value

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

    on_gpu = device == "cuda"
    where = "GPU" if on_gpu else "CPU"
    progress(20, f"Running inference on {where}")
    # `demix()` already reports per-chunk completion into `callback["progress"]`.
    # We were never passing one, so the bar sat at 20% for the entire run — on
    # CPU that reads as a bar that has hung. Report the real thing instead.
    cb: dict[str, float] = {}
    started = time.time()
    done = threading.Event()
    holder: dict[str, Any] = {}

    def run() -> None:
        try:
            holder["out"] = demix(
                config, model, mix, device,
                model_type=model_type, callback=cb,
            )
        except BaseException as exc:  # surfaced on the main thread below
            holder["err"] = exc
        finally:
            done.set()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    while not done.is_set():
        frac = float(cb.get("progress", 0.0))
        if frac > 0:
            # Hold back the last 5% for post-processing so the bar never
            # claims 100% before the stems exist on disk.
            progress(20 + frac * 75, f"Running inference on {where}")
        done.wait(0.5)
    t.join(timeout=5.0)

    if "err" in holder:
        raise holder["err"]
    waveforms = holder.get("out")
    if waveforms is None:
        raise RuntimeError("Inference produced no audio.")
    logger.info(
        "MSST separation took %.1fs for %s on %s",
        time.time() - started, model_id, device,
    )

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
        device = resolve_device()
        configure_runtime(device)
        # Autocast means float16 matmuls: a clear win on a GPU, and on a CPU a
        # liability — a lot of torch's ops have no usable float16 CPU kernel
        # and fall back to something slower than plain float32.
        sep_kwargs: dict[str, Any] = {
            "output_dir": output_dir,
            "output_format": output_format.upper(),
            "use_autocast": device == "cuda",
        }
        if device == "cpu":
            sep_kwargs.update(_cpu_separator_params())

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

            sep = self._cls(
                model_file_dir=str(ckpt.parent), **_supported_kwargs(self._cls, sep_kwargs)
            )
            _pin_device(sep, device)
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
            sep = self._cls(
                model_file_dir=str(registry_dir),
                **_supported_kwargs(self._cls, sep_kwargs),
            )
            _pin_device(sep, device)
            sep.load_model(model_filename=registry_name)

        # audio-separator exposes no per-chunk inference callback, so we cannot
        # report a percentage here the way the MSST path does. Say what is
        # actually true — which device is working, and that it is running —
        # instead of asserting "GPU" on a machine with no GPU.
        sep_device = "GPU" if device == "cuda" else "CPU"
        progress(10, f"Running inference on {sep_device}")

        # Real per-chunk progress, from the library's own tqdm loop. Without
        # it the bar sat at 10% for the whole run, which on a CPU reads as a
        # hung job, and the ETA derived from a stalled bar is fiction.
        restore_progress = _install_progress_hook(
            lambda frac: progress(10 + frac * 80, f"Running inference on {sep_device}")
        )

        start = time.time()
        produced = sep.separate(input_path)
        if restore_progress is not None:
            restore_progress()
        logger.info(
            "Separation took %.1fs for %s on %s",
            time.time() - start, model_id, sep_device.lower(),
        )

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
            # The chunk loop already reported up to 90%, so the stems are
            # written into the last tenth. Reporting from 10% again here made
            # the bar jump backwards.
            progress(90 + int((i + 1) / total * 10), f"Saved {stem}")

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
    allow_cpu_blocked: bool = False,
) -> list[dict[str, Any]]:
    progress = progress or (lambda p, s: None)
    # Apply before any model is constructed. Idempotent, and harmless for
    # checkpoints that were trained with the default factor of 4.
    _patch_melband_mlp_expansion()
    # Refuse a model this device cannot run BEFORE any weight is downloaded or
    # loaded. The queue checks this too, but the backend is the last line of
    # defence and must not depend on its callers having checked.
    #
    # `allow_cpu_blocked` is set by the Audio Repair workflow: its neural
    # model runs as one light pass wrapped in DSP, which is CPU-usable by
    # design and is not held to the separation-mode speed cutoff.
    device = resolve_device()
    configure_runtime(device)
    assert_runnable(model_id, device, allow_cpu_blocked=allow_cpu_blocked)
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