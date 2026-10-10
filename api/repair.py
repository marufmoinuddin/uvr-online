"""
Audio repair — corrective DSP for defective recordings.

This is deliberately **not** separation. Repair fixes defects in the recording
itself (clicks, clipping, hum, plosives, hiss), whereas the separation path
removes content (vocals, accompaniment) and is what needs a GPU model. Keeping
them apart matters for two reasons:

  * repair must never pull a checkpoint into VRAM — it is pure ffmpeg DSP, so
    it stays fast and costs nothing on a machine already busy separating;
  * the two have genuinely different failure modes and different validation.

`repair_file` returns a list holding a SINGLE stem, matching the shape
`separate_file` returns. Keeping the existing contract means the job queue, the
stem player and the download bundle all work unchanged — the alternative was a
second result shape threaded through every consumer.

Filter parameters were verified against ffmpeg 9.0.2 on real audio; several
first-pass values were rejected (`adeclick` overlap must be 50-95, `adeclip`
window 10-100), so do not "tidy" them back to round numbers without re-testing.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("uvr.repair")

ProgressFn = Callable[[float, str], None]

# Formats the UI offers for a repaired file. wav/flac are lossless; mp3 needs an
# explicit bitrate because the encoder default is low and would be a surprise
# after a "repair".
SUPPORTED_FORMATS = {"mp3": ["-b:a", "320k"], "wav": [], "flac": []}


class RepairError(ValueError):
    """An unusable repair request (unknown op, bad format, no ops)."""


def _op(
    key: str,
    label: str,
    description: str,
    chain: str,
) -> dict[str, str]:
    return {
        "key": key,
        "label": label,
        "description": description,
        "chain": chain,
    }


# The order here is also the order the filters are applied in, regardless of
# the order the user picked them. Defect removal runs before tonal work, and
# levelling runs last so it measures the signal the other ops actually left.
REPAIR_OPS: list[dict[str, str]] = [
    _op(
        "declick",
        "Remove clicks",
        "Strips impulsive ticks and digital clicks from the waveform.",
        "adeclick=window=40:overlap=75:arorder=2:threshold=2",
    ),
    _op(
        "declip",
        "Repair clipping",
        "Reconstructs samples that were flattened by a clipped recording.",
        "adeclip=window=55:overlap=75:threshold=10:hsize=1000",
    ),
    _op(
        "dehum",
        "Remove hum",
        "Cuts mains hum and rumble below 60 Hz, leaving the music intact.",
        "highpass=f=60",
    ),
    _op(
        "depop",
        "Tame plosives",
        "Softens harsh 'p' and 'b' transients on vocals.",
        "deesser=i=0.4:m=0.5:f=0.5:s=o",
    ),
    _op(
        "denoise",
        "Reduce hiss",
        "Steady broadband noise such as tape hiss or a noisy preamp.",
        "afftdn=nr=12:nf=-30:tn=1",
    ),
    _op(
        "gate",
        "Gate silence",
        "Drops noise floor between phrases so it does not run under the vocal.",
        "agate=threshold=0.05:ratio=2:attack=20:release=300:knee=2.8",
    ),
    _op(
        "normalize",
        "Even out level",
        "Evens the loudness across the track so quiet passages do not need boosting.",
        "dynaudnorm=f=250:g=15:p=0.95",
    ),
]

_OPS_BY_KEY = {op["key"]: op for op in REPAIR_OPS}
OP_KEYS = [op["key"] for op in REPAIR_OPS]


def list_ops() -> list[dict[str, str]]:
    """Repair operations for the UI (the internal filter chain is stripped)."""
    return [
        {k: v for k, v in op.items() if k != "chain"} for op in REPAIR_OPS
    ]


def resolve_ops(ops: list[str] | None) -> list[str]:
    """Validate requested ops and return them in canonical application order.

    Unknown keys are rejected rather than ignored: silently dropping a repair
    the user asked for would produce a file that still has the defect they were
    trying to remove, with no indication anything went wrong.
    """
    if not ops:
        raise RepairError("Choose at least one repair.")
    seen: set[str] = set()
    for key in ops:
        if key not in _OPS_BY_KEY:
            raise RepairError(
                f"Unknown repair '{key}'. Available: {', '.join(OP_KEYS)}"
            )
        seen.add(key)
    return [k for k in OP_KEYS if k in seen]


def build_filter_chain(ops: list[str]) -> str:
    """ffmpeg -af string for the validated, canonically ordered ops."""
    return ",".join(_OPS_BY_KEY[k]["chain"] for k in ops)


def _probe_duration(path: Path) -> Optional[float]:
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0", str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return float(proc.stdout.strip())
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


def _mean_volume(path: Path) -> Optional[float]:
    """Mean volume in dBFS, or None if it cannot be measured.

    Used as a guard against a filter chain that silently zeroes the stream: a
    'successful' repair that outputs silence is the exact failure mode a
    separate_file run can also produce, and it is just as bad here.
    """
    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect",
             "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in proc.stderr.splitlines():
        if "mean_volume:" in line:
            try:
                return float(line.split("mean_volume:")[1].replace("dB", "").strip())
            except (IndexError, ValueError):
                return None
    return None


def repair_file(
    input_path: str,
    output_dir: str,
    ops: list[str],
    output_format: str = "wav",
    progress: Optional[ProgressFn] = None,
) -> list[dict[str, Any]]:
    """Apply repair ops to one file. Returns a single-element stem list."""
    progress = progress or (lambda p, s: None)

    fmt = (output_format or "wav").lower()
    if fmt not in SUPPORTED_FORMATS:
        raise RepairError(
            f"Unsupported output format '{fmt}'. Allowed: "
            f"{', '.join(sorted(SUPPORTED_FORMATS))}"
        )

    ordered = resolve_ops(ops)
    chain = build_filter_chain(ordered)

    src = Path(input_path)
    if not src.is_file():
        raise RepairError("The uploaded file is missing.")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    job_id = out_dir.name
    out_name = f"{src.stem}_repaired.{fmt}"
    dest = out_dir / out_name

    progress(10, "Analyzing")
    source_duration = _probe_duration(src)

    cmd = ["ffmpeg", "-hide_banner", "-y", "-loglevel", "error",
           "-i", str(src), "-af", chain]
    cmd += SUPPORTED_FORMATS[fmt]
    cmd += ["-map_metadata", "-1", str(dest)]

    logger.info("Repairing %s with [%s] -> %s", src.name, ordered, dest.name)
    progress(35, "Repairing")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    except FileNotFoundError as exc:
        raise RepairError(
            "ffmpeg is not available on the worker, so repair cannot run."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RepairError("The repair timed out.") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        raise RepairError(
            "ffmpeg could not process this file"
            + (f": {detail[-1]}" if detail else ".")
        )

    if not dest.is_file() or dest.stat().st_size == 0:
        raise RepairError("The repair produced an empty file.")

    # ffmpeg reports success even when a filter chain annihilates the signal,
    # so verify the output is actually audible before reporting success.
    progress(80, "Verifying")
    mean = _mean_volume(dest)
    if mean is not None and mean < -60.0:
        dest.unlink(missing_ok=True)
        raise RepairError(
            "These repairs left the track silent, so nothing was written. "
            "Try a gentler combination — for example 'Gate silence' alone can "
            "close the gate on a very quiet recording."
        )

    # A repair must not change the running time; a mismatch means the file was
    # damaged rather than cleaned.
    if source_duration:
        out_duration = _probe_duration(dest)
        if out_duration and abs(out_duration - source_duration) > 0.5:
            dest.unlink(missing_ok=True)
            raise RepairError(
                "The repaired file does not match the original length "
                f"({out_duration:.1f}s vs {source_duration:.1f}s), so it was "
                "discarded."
            )

    progress(100, "Done")
    return [
        {
            "name": "Repaired",
            "url": f"/api/jobs/{job_id}/stems/{out_name}",
            "sizeBytes": dest.stat().st_size,
            "format": fmt,
        }
    ]