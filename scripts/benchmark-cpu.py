#!/usr/bin/env python3
"""Measure separation time per model, per device.

This is the MEASUREMENT that decides which models get `cpuOk: true` in the
catalogue. The answer is a property of the hardware, not of the model family,
so this has to be run on the machine the claim is about.

    # everything the catalogue marks as CPU-capable, plus the heavy ones
    python3 scripts/benchmark-cpu.py

    # a subset, and both devices
    python3 scripts/benchmark-cpu.py --models uvr_2hp,mbr_inst_v2 --devices cuda,cpu

    # longer clips
    python3 scripts/benchmark-cpu.py --clip-seconds 30

Each case runs in its own subprocess so that a model which hangs (or a native
crash in torch) cannot take the benchmark down, and so a per-case timeout is
possible — a CPU run of a RoFormer is exactly the thing that needs a ceiling.

Output is a markdown table:

    | model | arch | device | seconds | status |

Exit: 0 = every case finished, 1 = at least one case failed or timed out.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "api"

# Defaults so the script works from a checkout without a Docker container.
os.environ.setdefault("MODEL_CATALOG", str(API / "models.json"))
os.environ.setdefault("MODEL_STORE", str(ROOT / "models"))
os.environ.setdefault("OUTPUT_ROOT", str(ROOT / "output-benchmark"))


def _make_clip(path: Path, seconds: float, sample_rate: int = 44100) -> Path:
    """A synthetic but musical test clip.

    A sine sweep plus a couple of partials and some noise: enough spectral
    content that a separator actually does work (a silent or pure-tone clip
    would let some models short-circuit), and deterministic so two runs are
    comparable.
    """
    import numpy as np
    import soundfile as sf

    n = int(seconds * sample_rate)
    t = np.arange(n, dtype=np.float32) / sample_rate
    rng = np.random.default_rng(1234)

    mono = (
        0.30 * np.sin(2 * np.pi * 220.0 * t)
        + 0.20 * np.sin(2 * np.pi * 440.0 * t)
        + 0.15 * np.sin(2 * np.pi * 554.0 * t)
        + 0.05 * np.sin(2 * np.pi * 110.0 * t)
    )
    # A slow tremolo and a light noise bed: real material has dynamics.
    mono *= 0.7 + 0.3 * np.sin(2 * np.pi * 2.0 * t)
    mono += 0.01 * rng.standard_normal(n).astype(np.float32)

    stereo = np.stack([mono, mono * 0.9], axis=0).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    # soundfile.write expects (frames, channels) — the transpose matters: pass
    # it as (channels, frames) and libsndfile reads the sample count as the
    # channel count and refuses the file with "Format not recognised".
    sf.write(str(path), stereo.T, sample_rate, subtype="PCM_16")
    return path


def _run_one(model_id: str, device: str, clip: str, out_dir: str) -> int:
    """Run a single (model, device) case. This is the subprocess entry point."""
    sys.path.insert(0, str(API))
    os.environ["UVR_DEVICE"] = device

    import logging

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")

    from backend import separate_file

    started = time.perf_counter()
    try:
        stems = separate_file(model_id, clip, out_dir, "wav", False, False)
    except BaseException as exc:  # noqa: BLE001 - report and move on
        elapsed = time.perf_counter() - started
        print(
            json.dumps(
                {
                    "model": model_id,
                    "device": device,
                    "seconds": round(elapsed, 2),
                    "status": f"error: {exc}",
                    "stems": 0,
                }
            ),
            flush=True,
        )
        return 1
    elapsed = time.perf_counter() - started
    print(
        json.dumps(
            {
                "model": model_id,
                "device": device,
                "seconds": round(elapsed, 2),
                "status": "ok",
                "stems": len(stems),
            }
        ),
        flush=True,
    )
    return 0


def _env_facts() -> list[str]:
    """The environment facts that explain a slow CPU run."""
    facts: list[str] = []
    try:
        import torch

        facts.append(f"torch {torch.__version__}")
        facts.append(f"torch.get_num_threads() = {torch.get_num_threads()}")
        facts.append(f"torch.get_num_interop_threads() = {torch.get_num_interop_threads()}")
        facts.append(f"cuda available = {torch.cuda.is_available()}")
    except Exception as exc:  # pragma: no cover
        facts.append(f"torch unavailable: {exc}")
    facts.append(f"os.cpu_count() = {os.cpu_count()}")
    try:
        facts.append(f"sched_getaffinity = {len(os.sched_getaffinity(0))}")
    except AttributeError:
        pass
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "UVR_CPU_THREADS", "UVR_DEVICE"):
        if os.environ.get(var):
            facts.append(f"{var}={os.environ[var]}")
    try:
        raw = Path("/sys/fs/cgroup/cpu.max").read_text().strip()
        facts.append(f"cgroup cpu.max = {raw}")
    except OSError:
        pass
    return facts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", default="", help="comma-separated model ids (default: the CPU-capable set plus one RoFormer)")
    ap.add_argument("--devices", default="cuda,cpu", help="comma-separated devices")
    ap.add_argument("--clip-seconds", type=float, default=5.0)
    ap.add_argument("--timeout", type=float, default=900.0, help="per-case wall-clock ceiling in seconds")
    ap.add_argument(
        "--allow-blocked",
        action="store_true",
        help="also run the models the worker refuses in CPU mode (measurement only)",
    )
    ap.add_argument("--out", default="", help="write the markdown table here")
    args = ap.parse_args()

    sys.path.insert(0, str(API))
    from model_manager import manager as model_manager  # noqa: E402

    if args.models:
        model_ids = [m.strip() for m in args.models.split(",") if m.strip()]
    else:
        # The catalogue's CPU-capable set, plus one MelBand and one BS
        # RoFormer so the heavy end of the range is measured too.
        cpu_capable = sorted(m.id for m in model_manager.all() if m.cpu_ok)
        heavy = [m.id for m in model_manager.all() if "RoFormer" in (m.arch or "") and m.arch != "BS-PolarFormer"]
        model_ids = cpu_capable + heavy[:2]
    devices = [d.strip() for d in args.devices.split(",") if d.strip()]

    work = Path(os.environ["OUTPUT_ROOT"]) / "bench"
    work.mkdir(parents=True, exist_ok=True)
    clip = _make_clip(work / "clip.wav", args.clip_seconds)
    print(f"clip: {clip} ({args.clip_seconds}s)")
    print("environment:")
    for fact in _env_facts():
        print(f"  {fact}")
    print()

    rows: list[dict] = []
    for model_id in model_ids:
        rec = model_manager.get(model_id)
        arch = rec.arch if rec else "?"
        for device in devices:
            out_dir = work / f"{model_id}-{device}"
            out_dir.mkdir(parents=True, exist_ok=True)
            started = time.perf_counter()
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--run-one",
                model_id,
                device,
                str(clip),
                str(out_dir),
            ]
            child_env = {**os.environ, "UVR_DEVICE": device}
            if args.allow_blocked:
                # Measurement mode: time the models the worker refuses, so the
                # refusal has a number behind it.
                child_env["UVR_ALLOW_BLOCKED_MODELS"] = "1"
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=args.timeout,
                    env=child_env,
                )
            except subprocess.TimeoutExpired:
                rows.append(
                    {
                        "model": model_id,
                        "arch": arch,
                        "device": device,
                        "seconds": round(args.timeout, 1),
                        "status": f"timeout (>{args.timeout:.0f}s)",
                        "stems": 0,
                    }
                )
                print(f"{model_id:34s} {device:5s} TIMEOUT >{args.timeout:.0f}s", flush=True)
                continue

            row = None
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line.startswith("{") and '"seconds"' in line:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        pass
            if row is None:
                tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
                rows.append(
                    {
                        "model": model_id,
                        "arch": arch,
                        "device": device,
                        "seconds": round(time.perf_counter() - started, 1),
                        "status": f"crashed (exit {proc.returncode}): {' / '.join(tail)}",
                        "stems": 0,
                    }
                )
                print(f"{model_id:34s} {device:5s} CRASHED exit={proc.returncode}", flush=True)
                continue
            row["arch"] = arch
            rows.append(row)
            print(
                f"{model_id:34s} {device:5s} {row['seconds']:>8.1f}s  {row['status']}",
                flush=True,
            )

    table = ["| model | arch | device | seconds | status |", "|---|---|---|---|---|"]
    for r in rows:
        table.append(
            f"| {r['model']} | {r['arch']} | {r['device']} | {r['seconds']} | {r['status']} |"
        )
    markdown = "\n".join(table)
    print()
    print(markdown)
    if args.out:
        Path(args.out).write_text(markdown + "\n", encoding="utf-8")

    failed = any(r["status"] != "ok" for r in rows)
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--run-one":
        sys.exit(_run_one(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]))
    sys.exit(main())
