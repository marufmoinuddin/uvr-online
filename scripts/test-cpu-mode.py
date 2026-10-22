#!/usr/bin/env python3
"""CPU-mode tests.

CPU mode is only honest if three things hold. Each one has broken before:

1. **The device setting resolves the way the documentation says.** `auto` uses
   CUDA when there is one and the CPU otherwise; `cuda` REFUSES to run without
   a GPU rather than silently falling back (a silent fallback is how a
   one-minute job becomes an all-day one); `cpu` never touches the GPU even on
   a machine that has one.

2. **A model the catalogue does not mark CPU-capable is refused up front**,
   with an error that says why. Otherwise the user waits an hour and then
   gets a failure.

3. **A model that IS marked CPU-capable really produces valid stems on the
   CPU** — audible, full length, no NaN. A catalogue flag that was set from a
   guess rather than a measurement is worse than no flag at all.

Usage:
    python3 scripts/test-cpu-mode.py            # checks 1 and 2 (no torch needed)
    python3 scripts/test-cpu-mode.py --full     # also runs 3 (downloads a model)

Exit: 0 = pass, 1 = at least one check failed.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "api"

os.environ.setdefault("MODEL_CATALOG", str(API / "models.json"))
os.environ.setdefault("MODEL_STORE", str(ROOT / "models"))
os.environ.setdefault("OUTPUT_ROOT", str(ROOT / "output-cpu-test"))

sys.path.insert(0, str(API))

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))
    print(f"  {'✓' if ok else '✗'} {name}" + (f"  — {detail}" if detail and not ok else ""))


def _with_device(value: str | None):
    """Context manager that sets UVR_DEVICE for the duration of the block."""
    import contextlib

    @contextlib.contextmanager
    def cm():
        old = os.environ.get("UVR_DEVICE")
        if value is None:
            os.environ.pop("UVR_DEVICE", None)
        else:
            os.environ["UVR_DEVICE"] = value
        try:
            yield
        finally:
            if old is None:
                os.environ.pop("UVR_DEVICE", None)
            else:
                os.environ["UVR_DEVICE"] = old

    return cm()


def _device_tests() -> None:
    print("device resolution")
    from backend import resolve_device

    import torch

    has_cuda = bool(torch.cuda.is_available())

    with _with_device("cpu"):
        check(
            "UVR_DEVICE=cpu resolves to the CPU even when a GPU is present",
            resolve_device() == "cpu",
            f"got {resolve_device()!r} (cuda available: {has_cuda})",
        )

    with _with_device("auto"):
        got = resolve_device()
        check(
            "UVR_DEVICE=auto follows CUDA availability",
            got == ("cuda" if has_cuda else "cpu"),
            f"got {got!r}",
        )

    with _with_device(None):
        got = resolve_device()
        check(
            "an unset UVR_DEVICE behaves like auto",
            got == ("cuda" if has_cuda else "cpu"),
            f"got {got!r}",
        )

    with _with_device("CUDA"):
        check(
            "the value is case-insensitive",
            resolve_device() == "cuda" if has_cuda else True,
            "",
        )

    with _with_device("nonsense"):
        try:
            resolve_device()
            check("an invalid UVR_DEVICE is rejected", False, "no error raised")
        except RuntimeError as exc:
            check(
                "an invalid UVR_DEVICE is rejected",
                "nonsense" in str(exc),
                str(exc),
            )

    if not has_cuda:
        with _with_device("cuda"):
            try:
                resolve_device()
                check("UVR_DEVICE=cuda without a GPU fails loudly", False, "no error")
            except RuntimeError as exc:
                check(
                    "UVR_DEVICE=cuda without a GPU fails loudly",
                    "cuda" in str(exc).lower(),
                    str(exc),
                )
    else:
        with _with_device("cuda"):
            check(
                "UVR_DEVICE=cuda resolves to the GPU when one is present",
                resolve_device() == "cuda",
                "",
            )


def _thread_tests() -> None:
    print("CPU thread budget")
    from backend import effective_cpu_threads

    limit = effective_cpu_threads()
    check("the thread budget is at least 1", limit >= 1, f"got {limit}")

    try:
        affinity = len(os.sched_getaffinity(0))
    except AttributeError:
        affinity = os.cpu_count() or 1
    check(
        "the thread budget does not exceed the CPU affinity mask",
        limit <= affinity,
        f"budget {limit} > affinity {affinity}",
    )

    try:
        import torch

        before = torch.get_num_threads()
        from backend import configure_runtime

        info = configure_runtime("cpu")
        after = torch.get_num_threads()
        check(
            "configuring the CPU never INCREASES the thread count",
            after <= before,
            f"{before} -> {after}",
        )
        check(
            "the CPU path reports autocast disabled",
            info.get("autocast") is False,
            str(info),
        )
        check(
            "the CPU path reports TF32 disabled",
            info.get("tf32") is False,
            str(info),
        )
    except ImportError:
        print("  – torch not installed; skipped the runtime checks")


def _catalogue_tests() -> None:
    print("catalogue guard")
    from model_manager import manager as model_manager

    cpu_ok = [m for m in model_manager.all() if m.cpu_ok]
    blocked = [
        m for m in model_manager.all() if not m.cpu_ok and not m.unsupported
    ]

    check(
        "at least one model is marked CPU-capable",
        len(cpu_ok) > 0,
        f"got {len(cpu_ok)}",
    )
    check(
        "no unsupported model is marked CPU-capable",
        not [m.id for m in cpu_ok if m.unsupported],
        str([m.id for m in cpu_ok if m.unsupported]),
    )
    check(
        "the catalogue does not mark EVERY model CPU-capable",
        len(blocked) > 0,
        "every model is marked CPU-capable, which cannot be true",
    )

    from backend import assert_runnable

    if cpu_ok:
        try:
            assert_runnable(cpu_ok[0].id, "cpu")
            check(
                "a CPU-capable model is accepted on the CPU",
                True,
                "",
            )
        except RuntimeError as exc:
            check("a CPU-capable model is accepted on the CPU", False, str(exc))

    if blocked:
        try:
            assert_runnable(blocked[0].id, "cpu")
            check(
                "a non-CPU-capable model is REFUSED on the CPU",
                False,
                f"{blocked[0].id} was accepted",
            )
        except RuntimeError as exc:
            message = str(exc)
            check(
                "a non-CPU-capable model is REFUSED on the CPU",
                blocked[0].name in message,
                message,
            )
            check(
                "the refusal explains itself (mentions CPU mode)",
                "cpu" in message.lower(),
                message,
            )


def _make_clip(path: Path, seconds: float, sample_rate: int = 44100) -> Path:
    """A short musical test clip (see scripts/benchmark-cpu.py)."""
    import numpy as np
    import soundfile as sf

    n = int(seconds * sample_rate)
    t = np.arange(n, dtype=np.float32) / sample_rate
    rng = np.random.default_rng(7)
    mono = (
        0.30 * np.sin(2 * np.pi * 220.0 * t)
        + 0.20 * np.sin(2 * np.pi * 440.0 * t)
        + 0.15 * np.sin(2 * np.pi * 554.0 * t)
    )
    mono = (mono * (0.7 + 0.3 * np.sin(2 * np.pi * 2.0 * t))).astype(np.float32)
    mono += (0.01 * rng.standard_normal(n)).astype(np.float32)
    stereo = np.stack([mono, mono * 0.9], axis=0).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    # soundfile.write expects (frames, channels).
    sf.write(str(path), stereo.T, sample_rate, subtype="PCM_16")
    return path


def _inference_test(seconds: float = 5.0) -> None:
    """Run a real clip through a CPU-capable model and validate the stems."""
    print("CPU inference (real clip)")
    import numpy as np
    import soundfile as sf

    from backend import separate_file
    from model_manager import manager as model_manager

    candidates = [m for m in model_manager.all() if m.cpu_ok and not m.unsupported]
    if not candidates:
        check("a CPU-capable model exists to test with", False, "none in the catalogue")
        return
    # The smallest CPU-capable model: the test is about the CPU path, not
    # about how fast a particular architecture is.
    model = min(candidates, key=lambda m: m.speculative_mb or 0)
    print(f"  model: {model.id} ({model.arch})")

    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        clip = _make_clip(work / "clip.wav", seconds)
        out = work / "out"
        out.mkdir()

        import time

        started = time.perf_counter()
        try:
            stems = separate_file(model.id, str(clip), str(out), "wav", False, False)
        except Exception as exc:  # noqa: BLE001
            check(
                "the CPU run completes",
                False,
                f"{type(exc).__name__}: {exc}",
            )
            return
        elapsed = time.perf_counter() - started

        check("the CPU run produces stems", len(stems) > 0, f"got {len(stems)}")
        print(f"  elapsed: {elapsed:.1f}s for {seconds}s of audio")

        info = sf.info(str(clip))
        input_frames = info.frames
        input_sr = info.samplerate
        source, _ = sf.read(str(clip), always_2d=True)
        source_rms = float(np.sqrt(np.mean(source.astype(np.float64) ** 2)))

        # A per-stem loudness floor would be the wrong test: a separator
        # correctly writes near-silence for a stem the input does not
        # contain, and a synthetic sine mix has almost no bass in it. What
        # must hold is that the stems TOGETHER carry the source's energy —
        # a run that silently drops the mix fails this even when every stem
        # is "audible" on its own.
        total_energy = 0.0
        loudest = 0.0
        for stem in stems:
            path = out / Path(stem["url"]).name
            if not path.exists():
                check(f"stem {stem['name']!r} exists on disk", False, str(path))
                continue
            sinfo = sf.info(str(path))
            data, _ = sf.read(str(path), always_2d=True)
            rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
            total_energy += rms ** 2
            loudest = max(loudest, rms)

            check(
                f"stem {stem['name']!r} contains only finite samples",
                bool(np.isfinite(data).all()),
                "found NaN or inf",
            )
            # Duration drift: a stem that is shorter than the source is a
            # silent truncation, which sounds like a working separation.
            drift = abs(sinfo.frames - input_frames)
            check(
                f"stem {stem['name']!r} keeps the source duration",
                drift <= max(1, int(0.05 * input_frames)),
                f"{sinfo.frames} vs {input_frames} frames "
                f"({sinfo.samplerate} Hz vs {input_sr} Hz)",
            )

        combined_rms = float(np.sqrt(total_energy))
        ratio = combined_rms / source_rms if source_rms else 0.0
        check(
            "the stems together carry the source's energy",
            0.5 <= ratio <= 2.0,
            f"stems rms {combined_rms:.4f} vs source {source_rms:.4f} (ratio {ratio:.2f})",
        )
        check(
            "at least one stem is audible (above -60 dBFS)",
            loudest > 1e-3,
            f"loudest stem rms {loudest:.2e}",
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--full",
        action="store_true",
        help="also run a real separation on the CPU (downloads a model)",
    )
    ap.add_argument("--clip-seconds", type=float, default=5.0)
    args = ap.parse_args()

    _device_tests()
    _thread_tests()
    _catalogue_tests()

    if args.full:
        # The inference test must actually run on the CPU, whatever the
        # machine running the test has.
        os.environ["UVR_DEVICE"] = "cpu"
        _inference_test(args.clip_seconds)
    else:
        print("inference (real clip)")
        print("  – skipped (pass --full to run it)")

    failures = [r for r in results if r[0] == FAIL]
    print()
    if failures:
        print(f"FAILED — {len(failures)} of {len(results)} checks failed:")
        for _, name, detail in failures:
            print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))
        return 1
    print(f"OK — {len(results)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
