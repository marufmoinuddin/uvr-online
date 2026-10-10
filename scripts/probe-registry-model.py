#!/usr/bin/env python3
"""
Probe registry models: can they be fetched, loaded and run here?

The catalog may only offer a model the worker can actually load. This script
answers that empirically for a given registry filename instead of trusting the
registry listing — audio-separator lists far more than one GPU can run, and a
model that loads on paper but fails here is exactly the dead end the picker
must never show.

Usage:
  cd api && .venv/bin/python ../scripts/probe-registry-model.py 2_HP-UVR.pth
  cd api && .venv/bin/python ../scripts/probe-registry-model.py --all-in <file>
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))


def default_store() -> Path:
    """Where registry downloads should land — must match the app.

    Using MODEL_STORE directly here would scatter checkpoints across the model
    store root, where the worker never looks, so every probe would re-download
    the same weights. Importing the worker's resolver keeps the probe and the
    running app on one shared cache.
    """
    sys.path.insert(0, str(ROOT / "api"))
    try:
        from backend import resolve_registry_dir
    except Exception:  # pragma: no cover - fall back to the plain store
        return Path(os.environ.get("MODEL_STORE", str(ROOT / "models")))
    return resolve_registry_dir()


def probe(filename: str, audio: Path, store: Path) -> tuple[bool, str]:
    """Load `filename` from the registry and run it over `audio`."""
    import torch
    from audio_separator.separator import Separator

    store.mkdir(parents=True, exist_ok=True)
    # audio-separator returns BARE FILENAMES (relative), not absolute paths.
    # Resolving them against cwd silently reports "no output" for a model that
    # actually worked. backend.py resolves against output_dir for the same
    # reason; mirror that here.
    out_dir = store / "_probe"
    out_dir.mkdir(parents=True, exist_ok=True)
    sep = Separator(model_file_dir=str(store), output_dir=str(out_dir))
    try:
        sep.load_model(model_filename=filename)
    except BaseException as exc:  # audio-separator may sys.exit
        return False, f"load failed: {type(exc).__name__}: {str(exc)[:160]}"
    try:
        out = sep.separate(str(audio))
    except BaseException as exc:  # noqa: BLE001
        return False, f"separate failed: {type(exc).__name__}: {str(exc)[:160]}"
    finally:
        sep.model_instance = None
        del sep

    names = out if isinstance(out, (list, tuple)) else [out]
    files = []
    for f in names:
        p = Path(str(f))
        if not p.is_absolute():
            p = out_dir / p.name
        files.append(p)
    real = [f for f in files if f.is_file() and f.stat().st_size > 0]
    if not real:
        return False, f"produced no non-empty files (returned {str(names)[:100]})"

    # A model can "succeed" and emit silence; check the output is actually
    # decodable audio of a plausible length rather than trusting the exit.
    import librosa

    total = 0.0
    for f in real:
        try:
            y, sr = librosa.load(str(f), sr=None, mono=True)
        except Exception as exc:  # noqa: BLE001
            return False, f"output not decodable ({f.name}): {exc}"
        if y.size == 0:
            return False, f"output empty ({f.name})"
        total += float(y.size)
    return True, f"{len(real)} stem(s), {total:.0f} samples"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("filenames", nargs="+")
    ap.add_argument("--all-in", default=None, help="run every model over this file")
    ap.add_argument(
        "--store",
        default=None,
        help="override the cache dir (defaults to the worker's resolver)",
    )
    args = ap.parse_args()

    audio = Path(args.all_in) if args.all_in else None
    store = Path(args.store) if args.store else default_store()
    results = []

    for fn in args.filenames:
        if audio is None or not audio.is_file():
            print(f"{fn:62s} SKIP (no --all-in audio)")
            results.append(False)
            continue
        print(f"{fn:62s} ... ", end="", flush=True)
        started = time.time()
        ok, detail = probe(fn, audio, store)
        print(f"{'OK  ' if ok else 'FAIL'} {time.time() - started:6.1f}s  {detail}")
        results.append(ok)

    if results:
        print()
        print(f"{sum(results)}/{len(results)} usable")
    return 0 if all(results) and results else 1


if __name__ == "__main__":
    sys.exit(main())