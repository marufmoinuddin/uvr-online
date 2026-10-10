"""
Combined repair workflow — DSP operations plus at most one neural repair model.

Why this module exists
----------------------
`repair.py` is deliberately DSP-only and returns a ONE-ELEMENT stem list, which
every existing consumer (queue, player, download bundle, history) already
depends on. Adding neural models directly into it would put an audio-separator
dependency inside the ffmpeg module and break that contract. So this sits ABOVE
it as a coordinator and preserves the same one-result invariant.

Stage order (fixed, documented, recorded in the job record)
----------------------------------------------------------
    1. ffmpeg pre-ops        (lossless intermediate)
    2. neural repair model   (optional, exactly one)
    3. ffmpeg post-ops       (optional)
    4. encode ONCE to the requested delivery format
    5. publish exactly one repaired file

Rules that are not negotiable here:

* **The neural output is resolved by declared metadata**, never by position.
  `primaryStem` comes from the catalog and was measured by
  `scripts/test-repair-models.py`. A model emitting two files does not tell you
  which one is the repair; `Bleed + Instrumental`, `Back + Lead` and
  `Vocals + Other` are three different contracts. If the declared stem is
  missing the job FAILS — it never falls back to `outputs[0]`.

* **Intermediates stay lossless.** An intermediate MP3 fed into a model is a
  second-generation artefact, and the repair is judged on what came out.

* **At most one neural model.** Chaining several is not supported; a second one
  would need a declared per-stage stem mapping and its own acceptance tests.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Optional

from backend import canonical_stem_name, separate_file
import repair
from repair import RepairError, repair_file

logger = logging.getLogger("uvr.repair")

ProgressFn = Callable[[float, str], None]

# Which stage each operation belongs to.
#
# PRE: corrective-on-input. They fix defects that would otherwise confuse
# spectral analysis, and the model sees better material.
#   declick  impulsive ticks
#   declip   flattened samples are not recoverable by a neural model
#   dehum    steady low rumble, safely removed first
#   normalize  bring the model an input at a sane level
#
# POST: they act on what the model produced. Running `denoise` before a denoise
# model would pre-filter the very band the model is trying to learn, and
# `gate` would chop the phrase tails the model needs for context.
#   depop   harsh plosive transients
#   denoise steady broadband hiss
#   gate    noise floor between phrases
PRE_OPS: frozenset[str] = frozenset({"declick", "declip", "dehum", "normalize"})
POST_OPS: frozenset[str] = frozenset({"depop", "denoise", "gate"})

# Lossless working format for every intermediate.
INTERMEDIATE_FORMAT = "wav"


def _assert_ops_classified() -> None:
    """Every operation in repair.py must belong to a stage.

    Without this, adding an operation to REPAIR_OPS would leave it in neither
    set: `build_plan` would classify it as neither pre nor post and silently
    DROP it from the plan, so the user would get a job that did not do what
    they selected. Failing at import is the loud version.
    """
    missing = set(repair.OP_KEYS) - (PRE_OPS | POST_OPS)
    if missing:
        raise RuntimeError(
            f"repair operations not assigned to a workflow stage: "
            f"{', '.join(sorted(missing))}. Add each to PRE_OPS or POST_OPS in "
            "repair_workflow.py, or the operation will be silently dropped."
        )


_assert_ops_classified()


class RepairPlanError(RuntimeError):
    """Raised before any inference runs, when the plan cannot be honoured."""


def build_plan(
    ops: list[str],
    model_id: Optional[str],
    primary_stem: Optional[str],
    output_format: str = "wav",
) -> dict[str, Any]:
    """Split a flat op selection into pre/post stages and validate it.

    Returns a plain dict so it can be stored verbatim in the job record; a
    re-run must reproduce the same model, options and ordering.
    """
    requested = [o for o in (ops or []) if o]
    unknown = [o for o in requested if o not in (PRE_OPS | POST_OPS)]
    if unknown:
        raise RepairPlanError(
            f"Unknown repair operation(s): {', '.join(sorted(unknown))}. "
            f"Supported: {', '.join(sorted(PRE_OPS | POST_OPS))}"
        )

    if model_id and not primary_stem:
        # Without a declared stem there is no way to tell which output is the
        # repair, and guessing is the one thing this workflow must never do.
        raise RepairPlanError(
            f"Model '{model_id}' declares no repair.primaryStem, so its repaired "
            "output cannot be identified. Run scripts/test-repair-models.py to "
            "measure it before offering it here."
        )

    if not requested and not model_id:
        raise RepairPlanError(
            "Nothing to do: choose at least one fix-up or a neural repair model."
        )

    # Placement is NOT eligibility. PRE/POST only decide WHERE an operation
    # runs once a neural model is involved. On their own, every one of the
    # operations runs through the plain DSP path exactly as it did before the
    # hybrid existed — rejecting a standalone `denoise` or `gate` here would
    # silently remove capability the app has always had, on the strength of a
    # staging label that says nothing about whether the op works alone.
    pre = [o for o in requested if o in PRE_OPS] if model_id else list(requested)
    post = [o for o in requested if o in POST_OPS] if model_id else []

    return {
        "preOps": pre,
        "postOps": post,
        "modelId": model_id or None,
        "primaryStem": primary_stem or None,
        "outputFormat": (output_format or "wav").lower(),
        # Recorded so the history entry can state what actually ran.
        "stages": _stage_summary(bool(model_id), pre, post),
    }


def _stage_summary(has_model: bool, pre: list[str], post: list[str]) -> list[str]:
    """What actually runs, in order.

    Without a model there is no staging: every selected op is applied in the
    DSP-only path, so reporting `dsp-pre`/`dsp-post` would describe a pipeline
    that never ran.
    """
    if not has_model:
        return ["dsp-only"] if pre else []
    stages: list[str] = []
    if pre:
        stages.append("dsp-pre")
    stages.append("neural")
    if post:
        stages.append("dsp-post")
    return stages


def local_path(stem: dict[str, Any], out_dir: Path) -> Path:
    """Filesystem path for a stem the worker already produced.

    Stems are handed around as `{"name", "url", "sizeBytes", "format"}` with a
    URL of `/api/jobs/<id>/stems/<file>`. Recover the filename from the last
    segment — URL-decoded, because MDX De-Reverb writes a stem literally named
    "No dry" and its raw space is not a legal path character.
    """
    url = stem.get("url") or ""
    fname = urllib.parse.unquote(url.rsplit("/", 1)[-1])
    if not fname:
        raise RepairPlanError(f"Stem {stem.get('name')!r} has no usable URL: {url!r}")
    path = out_dir / fname
    if not path.is_file():
        raise RepairPlanError(
            f"Expected stem file is missing: {path.name}. The backend reported it "
            "but it is not on disk."
        )
    return path


def resolve_repair_output(
    stems: list[dict[str, Any]],
    primary_stem: str,
    model_id: str,
) -> dict[str, Any]:
    """Pick the repaired stem by declared name. Never by position.

    Raises rather than substituting: returning the wrong file while reporting
    success is the exact failure mode this project exists to eliminate.
    """
    want = canonical_stem_name(primary_stem).lower()
    for stem in stems:
        if canonical_stem_name(stem.get("name", "")).lower() == want:
            return stem
    available = ", ".join(
        sorted({canonical_stem_name(s.get("name", "")) for s in stems})
    )
    raise RepairPlanError(
        f"Model '{model_id}' was asked for its '{primary_stem}' output but did "
        f"not produce one. It produced: {available or 'nothing'}. The declared "
        "primaryStem no longer matches this model — re-run "
        "scripts/test-repair-models.py."
    )


def execute_repair_job(
    input_path: str,
    output_dir: str,
    plan: dict[str, Any],
    model_manager: Any,
    progress: Optional[ProgressFn] = None,
) -> list[dict[str, Any]]:
    """Run the whole workflow and return a ONE-element stem list."""
    progress = progress or (lambda p, s: None)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Every intermediate lives in a temp dir so a failed model run cannot leave
    # half-repaired audio sitting next to the real results.
    work = Path(tempfile.mkdtemp(prefix="repair-", dir=out_dir))
    try:
        current = Path(input_path)
        stage = 0
        total_stages = len(plan["stages"])

        # -- 1. ffmpeg pre -------------------------------------------------
        if plan["preOps"]:
            progress(0.05, f"Applying {len(plan['preOps'])} fix-up(s)")
            stems = repair_file(
                str(current), str(work / "pre"), plan["preOps"],
                INTERMEDIATE_FORMAT,
                lambda p, s: progress(stage_progress(stage, total_stages, p), s),
            )
            current = local_path(stems[0], work / "pre")
            stage += 1

        # -- 2. neural -----------------------------------------------------
        if plan["modelId"]:
            progress(0.15, "Running neural repair model")
            rec = model_manager.get(plan["modelId"])
            if rec is None:
                raise RepairPlanError(f"Unknown model '{plan['modelId']}'.")
            if rec.unsupported:
                raise RepairPlanError(
                    f"'{rec.name}' cannot be used: {rec.unsupported}"
                )
            declared = rec.repair_primary_stem
            if declared != plan["primaryStem"]:
                # The catalog moved under us; refuse rather than guess.
                raise RepairPlanError(
                    f"'{rec.name}' now declares primaryStem "
                    f"{declared!r}, but this job was planned for "
                    f"{plan['primaryStem']!r}."
                )
            stems = separate_file(
                plan["modelId"], str(current), str(work / "neural"),
                INTERMEDIATE_FORMAT,
                progress=lambda p, s: progress(
                    stage_progress(stage, total_stages, p * 0.8), s
                ),
            )
            chosen = resolve_repair_output(stems, plan["primaryStem"], plan["modelId"])
            current = local_path(chosen, work / "neural")
            stage += 1

        # -- 3. ffmpeg post ------------------------------------------------
        if plan["postOps"]:
            progress(0.9, f"Finishing with {len(plan['postOps'])} fix-up(s)")
            stems = repair_file(
                str(current), str(work / "post"), plan["postOps"],
                INTERMEDIATE_FORMAT,
                lambda p, s: progress(0.9 + p * 0.08, s),
            )
            current = local_path(stems[0], work / "post")
            stage += 1

        # -- 4. encode ONCE to the delivery format -------------------------
        progress(0.98, "Encoding")
        fmt = plan["outputFormat"]
        out_name = f"{Path(input_path).stem}_repaired.{fmt}"
        dest = out_dir / out_name
        _encode_once(current, dest, fmt)

        # Same shape `repair_file()` returns, so the queue, player, bundle and
        # history need no changes at all.
        return [{
            "name": "Repaired",
            "url": f"/api/jobs/{out_dir.name}/stems/{out_name}",
            "sizeBytes": dest.stat().st_size,
            "format": fmt,
        }]
    finally:
        # Intermediates are never part of the result set, so they must not
        # survive: a failed run used to be able to leave them beside the output.
        shutil.rmtree(work, ignore_errors=True)


def stage_progress(stage: int, total: int, frac: float) -> float:
    """Map a stage-local 0..1 progress onto the overall job."""
    if total <= 0:
        return 0.0
    base = stage / total
    return max(0.0, min(1.0, base + (frac / total)))


def _encode_once(src: Path, dest: Path, fmt: str) -> None:
    """Transcode the final intermediate. This is the only encode in the chain."""
    import subprocess

    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src)]
    if fmt == "mp3":
        cmd += ["-c:a", "libmp3lame", "-b:a", "320k"]
    elif fmt == "flac":
        cmd += ["-c:a", "flac"]
    else:
        cmd += ["-c:a", "pcm_s16le"]
    cmd.append(str(dest))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not dest.exists():
        raise RepairError(
            f"Could not encode the repaired audio to {fmt}: "
            f"{(proc.stderr or '').strip()[:200]}"
        )