#!/usr/bin/env python3
"""
Tests for api/repair.py — run against real ffmpeg, not mocks.

A repair is DSP: "the command exited 0" proves almost nothing. What matters is
that the output is audible, the same length as the input, and that a filter
chain which silences the signal is caught rather than reported as success.

Usage: cd api && .venv/bin/python ../scripts/test-repair.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

import repair  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))


def make_input(path: Path, seconds: int = 4) -> None:
    """A tone mixed with pink noise — enough to survive gate/normalise."""
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-f", "lavfi", "-i", f"anoisesrc=d={seconds}:c=pink:a=0.05",
            "-filter_complex", "[0][1]amix=inputs=2",
            "-ac", "2", "-ar", "44100", str(path),
        ],
        check=True,
        capture_output=True,
    )


def duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(proc.stdout.strip())


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        src = tmp / "clip.wav"
        make_input(src)
        src_dur = duration(src)

        # --- every single op must run and produce audible, full-length audio
        for op in repair.OP_KEYS:
            out = tmp / f"out_{op}"
            try:
                stems = repair.repair_file(str(src), str(out), [op], "wav")
            except Exception as exc:  # noqa: BLE001
                check(f"op '{op}' runs", False, f"{type(exc).__name__}: {exc}")
                continue
            produced = out / "clip_repaired.wav"
            check(
                f"op '{op}' runs",
                len(stems) == 1 and produced.is_file() and produced.stat().st_size > 0,
                f"stems={len(stems)}",
            )
            if produced.is_file():
                d = duration(produced)
                mean = repair._mean_volume(produced)
                check(
                    f"op '{op}' keeps duration, stays audible",
                    abs(d - src_dur) < 0.5 and (mean is None or mean > -60),
                    f"dur={d:.2f} (src {src_dur:.2f}) mean={mean}",
                )

        # --- chained ops
        out = tmp / "chained"
        stems = repair.repair_file(
            str(src), str(out), ["normalize", "denoise", "declick"], "wav"
        )
        check(
            "chained ops apply in canonical order",
            len(stems) == 1 and (out / "clip_repaired.wav").is_file(),
            f"order={repair.resolve_ops(['normalize', 'denoise', 'declick'])}",
        )

        # --- each output format actually encodes
        for fmt in ("wav", "mp3", "flac"):
            out = tmp / f"fmt_{fmt}"
            try:
                repair.repair_file(str(src), str(out), ["denoise"], fmt)
                produced = out / f"clip_repaired.{fmt}"
                probe = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", "a:0",
                     "-show_entries", "stream=codec_name", "-of", "csv=p=0",
                     str(produced)],
                    capture_output=True, text=True,
                )
                check(
                    f"format '{fmt}' encodes audio",
                    produced.is_file() and probe.returncode == 0,
                    f"codec={probe.stdout.strip() or 'none'}",
                )
            except Exception as exc:  # noqa: BLE001
                check(f"format '{fmt}' encodes audio", False, str(exc)[:80])

        # --- rejections
        for bad, label in [(["not_a_real_op"], "unknown op"), ([], "no ops")]:
            try:
                repair.repair_file(str(src), str(tmp / "bad"), bad, "wav")
                check(f"rejects {label}", False, "no error raised")
            except repair.RepairError as exc:
                check(f"rejects {label}", True, str(exc)[:60])
            except Exception as exc:  # noqa: BLE001
                check(f"rejects {label}", False, f"wrong type {type(exc).__name__}")

        try:
            repair.repair_file(str(src), str(tmp / "bad2"), ["denoise"], "ogg")
            check("rejects unsupported format", False, "no error raised")
        except repair.RepairError as exc:
            check("rejects unsupported format", True, str(exc)[:60])

        # --- canonical ordering + de-duplication
        resolved = repair.resolve_ops(["normalize", "denoise", "normalize", "declick"])
        check(
            "resolve_ops de-duplicates and orders canonically",
            resolved == ["declick", "denoise", "normalize"],
            str(resolved),
        )

        # --- a silent input must be rejected, not returned as success
        silent = tmp / "silence.wav"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
             "-i", "anullsrc=r=44100:cl=stereo", "-t", "3", str(silent)],
            check=True, capture_output=True,
        )
        try:
            repair.repair_file(str(silent), str(tmp / "sil"), ["normalize"], "wav")
            check("rejects silent output", False, "reported success on silence")
        except repair.RepairError as exc:
            check("rejects silent output", True, str(exc)[:70])

        # --- ops metadata is UI-safe (no filter chain leaked)
        ops = repair.list_ops()
        check(
            "list_ops hides internal filter chains",
            all("chain" not in o for o in ops) and len(ops) == len(repair.OP_KEYS),
            f"{len(ops)} ops",
        )

    width = max(len(n) for _, n, _ in results)
    for level, name, detail in results:
        print(f"{'✓' if level == PASS else '✗'} {name.ljust(width)}  {detail}")
    failures = [r for r in results if r[0] == FAIL]
    print()
    if failures:
        print(f"FAILED — {len(failures)}/{len(results)} checks failed")
        return 1
    print(f"OK — {len(results)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())