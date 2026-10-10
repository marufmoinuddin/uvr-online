#!/usr/bin/env python3
"""
Negative tests for verify-catalog.py.

A verifier that only ever passes is worthless. This injects each bug class the
catalog has actually suffered, into throwaway copies of the two catalogs, and
asserts the verifier FAILS. Each case copies the real files to a temp tree and
mutates the copies — the working tree is never touched.

Usage: python3 scripts/test-verify-catalog.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts" / "verify-catalog.py"
WORKER_CATALOG = ROOT / "api" / "models.json"
UI_CATALOG = ROOT / "web" / "src" / "lib" / "models.ts"

RUNNABLE = "becruily_deux"  # present and fetchable in both catalogs


def _run(tree: Path) -> tuple[int, str]:
    # Must invoke the COPY inside the sandbox: the verifier locates its
    # catalogs relative to its own __file__, so running the repo copy would
    # silently verify the real tree and pass every case.
    proc = subprocess.run(
        [sys.executable, str(tree / "scripts" / VERIFIER.name)],
        capture_output=True,
        text=True,
        cwd=tree,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _sandbox(tmp: Path) -> Path:
    (tmp / "api").mkdir()
    (tmp / "scripts").mkdir()
    (tmp / "web" / "src" / "lib").mkdir(parents=True)
    shutil.copy(WORKER_CATALOG, tmp / "api" / "models.json")
    shutil.copy(UI_CATALOG, tmp / "web" / "src" / "lib" / "models.ts")
    shutil.copy(VERIFIER, tmp / "scripts" / VERIFIER.name)
    return tmp


def _edit_worker(tree: Path, fn) -> None:
    p = tree / "api" / "models.json"
    data = json.loads(p.read_text())
    fn(data)
    p.write_text(json.dumps(data, indent=2))


def _edit_ui(tree: Path, old: str, new: str) -> None:
    p = tree / "web" / "src" / "lib" / "models.ts"
    text = p.read_text()
    if old not in text:
        raise AssertionError(f"fixture text not found in models.ts: {old!r}")
    p.write_text(text.replace(old, new, 1))


# --- cases: (name, mutate) ------------------------------------------------

def c_worker_only_id(t: Path) -> None:
    def f(d):
        entry = dict(d[RUNNABLE])
        entry["name"] = "Ghost Model"
        d["ghost_model"] = entry
    _edit_worker(t, f)


def c_unsupported_missing_in_ui(t: Path) -> None:
    def f(d):
        d["mel_band_roformer_fv9"].pop("unsupported", None)
    _edit_worker(t, f)


def c_unsupported_missing_in_worker(t: Path) -> None:
    _edit_ui(
        t,
        '    unsupported:\n      "No download source is configured for this model yet, so it cannot be fetched.",\n',
        "",
    )


def c_no_fetch_path(t: Path) -> None:
    def f(d):
        d["bs_roformer_voc_resurrection"].pop("registry", None)
        d["bs_roformer_voc_resurrection"].pop("download", None)
    _edit_worker(t, f)


def c_scene_default_unsupported(t: Path) -> None:
    # Mark it unsupported in BOTH catalogs so the parity check stays green and
    # the scene-default check is what has to catch this.
    _edit_worker(t, lambda d: d.__setitem__(RUNNABLE, {**d[RUNNABLE], "unsupported": True}))
    _edit_ui(t, 'id: "becruily_deux",', 'unsupported: "no longer runnable",\n    id: "becruily_deux",')


def c_scene_default_missing(t: Path) -> None:
    _edit_ui(t, 'defaultModelId: "becruily_deux"', 'defaultModelId: "does_not_exist"')


def c_scene_default_wrong_target(t: Path) -> None:
    # Swap ONLY the vocal-remover scene's default to a 4-stem model, leaving
    # every other scene untouched, so exactly one scene-target check fires.
    p = t / "web" / "src" / "lib" / "models.ts"
    text = p.read_text()
    marker = 'key: "vocal-remover"'
    i = text.index(marker)
    j = text.index('defaultModelId: "becruily_deux"', i)
    text = text[:j] + 'defaultModelId: "htdemucs_4stem"' + text[j + len('defaultModelId: "becruily_deux"'):]
    p.write_text(text)


def c_ui_only_not_ensemble(t: Path) -> None:
    # A stray UI entry with no worker counterpart and no ensemble flag.
    _edit_ui(
        t,
        "export const MODEL_CATALOG: Model[] = [...BASE_MODELS, ...ENSEMBLE_PRESETS];",
        "const STRAY: Model = {\n  id: \"stray_model\",\n  name: \"Stray\",\n"
        "  arch: \"X\",\n  target: \"dual\",\n  tags: [],\n  sizeMB: 0,\n"
        '  source: "x",\n};\n\n'
        "export const MODEL_CATALOG: Model[] = [...BASE_MODELS, ...ENSEMBLE_PRESETS, STRAY];",
    )


def c_repair_scene_with_model(t: Path) -> None:
    # A repair scene must not declare a default model — it runs ffmpeg DSP and
    # downloads nothing, so a default would be a lie the UI would act on.
    _edit_ui(
        t,
        '    key: "audio-repair",',
        '    key: "audio-repair",\n    defaultModelId: "becruily_deux",',
    )


def c_instrument_target_missing_in_ui(t: Path) -> None:
    # The UI claims htdemucs_6s can isolate guitar, the worker says it cannot.
    # The picker would offer Guitar and then the job would fail after upload.
    _edit_ui(
        t,
        'instrumentTargets: ["drums", "bass", "guitar", "piano"],',
        'instrumentTargets: ["drums", "bass"],',
    )


def c_instrument_target_extra_in_ui(t: Path) -> None:
    # The reverse drift: UI advertises a stem the worker never observed.
    _edit_ui(
        t,
        'instrumentTargets: ["guitar"],',
        'instrumentTargets: ["guitar", "strings"],',
    )


CASES = [
    ("model in worker catalog but not in UI", c_worker_only_id),
    ("unsupported flag missing from UI", c_unsupported_missing_in_ui),
    ("unsupported flag missing from worker", c_unsupported_missing_in_worker),
    ("worker entry with no download/registry", c_no_fetch_path),
    ("scene default model is unsupported", c_scene_default_unsupported),
    ("scene default model not in catalog", c_scene_default_missing),
    ("scene default target not allowed by scene", c_scene_default_wrong_target),
    ("UI-only id not marked ensemble", c_ui_only_not_ensemble),
    ("repair scene declaring a default model", c_repair_scene_with_model),
    ("instrument target dropped from UI", c_instrument_target_missing_in_ui),
    ("instrument target added in UI only", c_instrument_target_extra_in_ui),
]


def main() -> int:
    failures = []

    # 0. the untouched tree must pass — otherwise the negative cases prove nothing
    with tempfile.TemporaryDirectory() as d:
        tree = _sandbox(Path(d))
        code, out = _run(tree)
        if code != 0:
            failures.append(("baseline (must PASS)", out.strip()))
        else:
            print("✓ baseline: clean tree passes")

    for name, mutate in CASES:
        with tempfile.TemporaryDirectory() as d:
            tree = _sandbox(Path(d))
            mutate(tree)
            code, out = _run(tree)
            if code == 0:
                failures.append((name, "verifier PASSED but should have FAILED"))
            else:
                first = next(
                    (ln for ln in out.splitlines() if ln.startswith("✗")), "?"
                )
                print(f"✓ caught: {name}")
                print(f"    {first.strip()[:150]}")

    print()
    if failures:
        print(f"FAILED — {len(failures)} case(s) not detected:")
        for name, detail in failures:
            print(f"  ✗ {name}: {detail[:200]}")
        return 1
    print(f"OK — {len(CASES)} negative cases caught, baseline still passes")
    return 0


if __name__ == "__main__":
    sys.exit(main())