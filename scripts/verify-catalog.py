#!/usr/bin/env python3
"""
Cross-check the two model catalogs.

The worker's catalog (`api/models.json`) and the UI catalog
(`web/src/lib/models.ts`) must agree. They have drifted three times already:
a model or an `unsupported` flag landed in one file and not the other, so the
picker offered an entry the worker then refused to load (or hid one that
worked). Nothing else in the build catches that, which is why this script
exists.

Checks
  1. id sets match (ensemble presets are UI-only by design and are exempt)
  2. `unsupported` is present on exactly the same ids in both files
  3. every worker entry is fetchable: `download.files` OR `registry`
     OR `unsupported`  (otherwise it is a dead end the picker offers)
  4. every scene `defaultModelId` exists, is runnable, and its target is
     allowed by that scene
  5. UI-only ids are all ensemble presets

Usage:  python3 scripts/verify-catalog.py [--json]
Exit:   0 = consistent, 1 = at least one violation
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER_CATALOG = ROOT / "api" / "models.json"
UI_CATALOG = ROOT / "web" / "src" / "lib" / "models.ts"

OK, WARN, FAIL = "PASS", "WARN", "FAIL"


# --- UI catalog parsing ----------------------------------------------------
# models.ts is TypeScript, so it cannot be JSON-parsed. Rather than pull in a
# TS toolchain we split the two literal arrays on brace depth and read the
# fields we need. Anchoring on `const BASE_MODELS` / `const ENSEMBLE_PRESETS`
# matters: `id:` appears in both arrays, so a naive scan would merge them.


def _array_body(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def _objects(body: str) -> list[str]:
    """Return each top-level `{...}` object literal in `body`."""
    out, depth, start = [], 0, None
    for i, ch in enumerate(body):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                out.append(body[start : i + 1])
                start = None
    return out


def _field(obj: str, key: str) -> str | None:
    m = re.search(rf"\b{key}\s*:\s*(?:\"([^\"]*)\"|'([^']*)'|([^,}}\n]+))", obj)
    if not m:
        return None
    return (m.group(1) or m.group(2) or m.group(3) or "").strip()


def _match_array(obj: str, key: str) -> str:
    """Body of a `key: ["a", "b"]` array, or "" when absent."""
    m = re.search(rf"\b{key}\s*:\s*\[([^\]]*)\]", obj)
    return m.group(1) if m else ""


def _repair_block(obj: str) -> str | None:
    """Body of the `repair: { ... }` object inside a model entry, or None."""
    m = re.search(r"\brepair\s*:\s*\{(.*?)\n\s*\}", obj, re.S)
    return m.group(1) if m else None


def _repair_of(obj: str) -> dict | None:
    """Parse a model's repair capability out of models.ts.

    Returns None when the model declares no repair at all — which is the normal
    case, not an error. Eligibility in the Audio Repair scene is this field, so
    the two catalogs disagreeing about its absence would hide a model on one
    side of the app only.
    """
    block = _repair_block(obj)
    if block is None:
        return None
    cats = re.search(r"categories\s*:\s*\[([^\]]*)\]", block)
    stem = re.search(r"primaryStem\s*:\s*[\"']([^\"']*)[\"']", block)
    scope = re.search(r"inputScope\s*:\s*[\"']([^\"']*)[\"']", block)
    chans = re.search(r"preservesChannels\s*:\s*(true|false)", block)
    return {
        "categories": sorted(re.findall(r"\"([^\"]+)\"", cats.group(1))) if cats else [],
        "primaryStem": stem.group(1) if stem else None,
        "inputScope": scope.group(1) if scope else None,
        "preservesChannels": chans.group(1) == "true" if chans else None,
    }


def parse_ui_catalog(source: str) -> dict:
    base = _array_body(source, "const BASE_MODELS", "const ENSEMBLE_PRESETS")
    ens = _array_body(
        source, "const ENSEMBLE_PRESETS", "export const MODEL_CATALOG"
    )
    scenes_body = source[source.index("export const SCENES") :]

    models: dict[str, dict] = {}
    for obj in _objects(base) + _objects(ens):
        model_id = _field(obj, "id")
        if not model_id:
            continue
        models[model_id] = {
            "unsupported": "unsupported" in obj,
            "ensemble": (_field(obj, "ensemble") or "").lower() == "true",
            "target": _field(obj, "target"),
            # Whether the model may run in CPU mode. ABSENT MEANS FALSE — the
            # safe default — so only the explicitly-true models count. The
            # worker treats a missing flag exactly the same way.
            "cpuOk": (_field(obj, "cpuOk") or "").lower() == "true",
            # Instrument stems this model was OBSERVED to emit. The Instrument
            # Extractor scene offers exactly this set, so a mismatch between the
            # two catalogs means the picker advertises a stem the worker will
            # refuse after the upload.
            "instrumentTargets": sorted(
                set(re.findall(r'"([^"]+)"', _match_array(obj, "instrumentTargets")))
            ),
            # Explicit neural-repair capability. The Audio Repair scene offers a
            # model iff this is truthy, so a disagreement between the two files
            # would hide a repair model in one half of the app only.
            "repair": _repair_of(obj),
        }

    scenes: dict[str, dict] = {}
    for obj in _objects(scenes_body):
        key = _field(obj, "key")
        if not key:
            continue
        targets = re.search(r"allowedTargets\s*:\s*\[([^\]]*)\]", obj)
        scenes[key] = {
            "defaultModelId": _field(obj, "defaultModelId"),
            "allowedTargets": re.findall(r"\"([^\"]+)\"", targets.group(1))
            if targets
            else [],
            # Repair scenes run ffmpeg DSP and legitimately have no model.
            "repair": (_field(obj, "repair") or "").lower() == "true",
            # Instrument scenes isolate one stem and need the instrument picker.
            "instrument": (_field(obj, "instrument") or "").lower() == "true",
        }
    return {"models": models, "scenes": scenes}


# --- checks ----------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    rows: list[tuple[str, str, str]] = []

    def check(level: str, name: str, detail: str = "") -> None:
        rows.append((level, name, detail))

    worker = json.loads(WORKER_CATALOG.read_text())
    ui = parse_ui_catalog(UI_CATALOG.read_text())
    ui_models, scenes = ui["models"], ui["scenes"]

    # 1. id sets -----------------------------------------------------------
    worker_ids, ui_ids = set(worker), set(ui_models)
    ensembles = {i for i, m in ui_models.items() if m["ensemble"]}
    ui_only = ui_ids - worker_ids
    worker_only = worker_ids - ui_ids

    # Ensemble presets are computed locally (they fuse existing jobs), so they
    # legitimately have no worker catalog entry.
    unexpected_ui_only = ui_only - ensembles
    if unexpected_ui_only:
        check(
            FAIL,
            "ids: UI-only entries with no worker entry",
            ", ".join(sorted(unexpected_ui_only)),
        )
    else:
        check(
            OK,
            "ids: UI-only entries are all ensemble presets",
            f"{len(ensembles)} exempt",
        )

    missing_in_ui = worker_only - ui_ids
    if missing_in_ui:
        check(FAIL, "ids: in worker catalog but not in UI", ", ".join(sorted(missing_in_ui)))
    else:
        check(OK, "ids: every worker model is in the UI catalog")

    if worker_only or unexpected_ui_only:
        pass  # already reported above with the specific offender
    else:
        check(OK, "ids: catalogs in sync", f"{len(worker_ids)} shared")

    # 2. unsupported parity ------------------------------------------------
    w_unsup = {i for i, m in worker.items() if m.get("unsupported")}
    u_unsup = {i for i, m in ui_models.items() if m["unsupported"]}
    if w_unsup == u_unsup:
        check(OK, "unsupported: flags match in both files", f"{len(w_unsup)} flagged")
    else:
        only_w = sorted(w_unsup - u_unsup)
        only_u = sorted(u_unsup - w_unsup)
        check(
            FAIL,
            "unsupported: flags differ between catalogs",
            f"worker-only={only_w or '-'} ui-only={only_u or '-'}",
        )

    # 2b. CPU-capability parity --------------------------------------------
    # The worker REFUSES a model in CPU mode unless the catalogue says it may
    # run there. If the two catalogs disagree, the picker either offers a
    # model the worker will reject after the upload, or hides one that works.
    w_cpu = {i for i, m in worker.items() if m.get("cpuOk")}
    u_cpu = {i for i, m in ui_models.items() if m["cpuOk"]}
    if w_cpu == u_cpu:
        check(
            OK,
            "cpu: CPU-capable flags match in both files",
            f"{len(w_cpu)} flagged",
        )
    else:
        only_w = sorted(w_cpu - u_cpu)
        only_u = sorted(u_cpu - w_cpu)
        check(
            FAIL,
            "cpu: CPU-capable flags differ between catalogs",
            f"worker-only={only_w or '-'} ui-only={only_u or '-'}",
        )

    # A model that cannot run at all must not also be advertised as
    # CPU-capable: the worker refuses it for a different reason, but the UI
    # would show it as available on a CPU.
    bad_cpu = sorted(i for i in w_cpu if worker[i].get("unsupported"))
    if bad_cpu:
        check(
            FAIL,
            "cpu: unsupported models are marked CPU-capable",
            ", ".join(bad_cpu),
        )
    else:
        check(OK, "cpu: no unsupported model is marked CPU-capable")

    # 3. fetchability ------------------------------------------------------
    unfetchable = [
        i
        for i, m in worker.items()
        if not (m.get("download", {}).get("files") or m.get("registry") or m.get("unsupported"))
    ]
    if unfetchable:
        check(
            FAIL,
            "fetchable: worker entries with no download/registry/unsupported",
            ", ".join(sorted(unfetchable)),
        )
    else:
        check(OK, "fetchable: every worker entry can be fetched or is flagged")

    # 4. scene defaults ----------------------------------------------------
    bad_missing, bad_unsup, bad_target = [], [], []
    for scene, meta in scenes.items():
        default = meta["defaultModelId"]
        if meta["repair"]:
            # A repair scene has no model — but it must still not claim one
            # that does not exist, and it must not offer models to choose.
            if default:
                bad_missing.append(
                    f"{scene}: repair scene must not set a defaultModelId"
                )
            continue
        if not default:
            bad_missing.append(f"{scene}: no defaultModelId")
            continue
        if default not in ui_models:
            bad_missing.append(f"{scene} -> {default} (not in catalog)")
            continue
        if default in u_unsup:
            bad_unsup.append(f"{scene} -> {default}")
            continue
        target = ui_models[default]["target"]
        allowed = meta["allowedTargets"]
        if allowed and target not in allowed:
            bad_target.append(f"{scene} -> {default} (target {target} not in {allowed})")

    if bad_missing:
        check(FAIL, "scenes: defaultModelId not in catalog", "; ".join(bad_missing))
    else:
        check(OK, "scenes: every defaultModelId exists", f"{len(scenes)} scenes")
    if bad_unsup:
        check(FAIL, "scenes: default model is unsupported", "; ".join(bad_unsup))
    else:
        check(OK, "scenes: every default model is runnable")
    if bad_target:
        check(FAIL, "scenes: default model target not allowed", "; ".join(bad_target))
    else:
        check(OK, "scenes: every default model passes its own target filter")

    # 4b. instrument parity -----------------------------------------------
    # The instrument scene's whole contract is "offer only stems the worker can
    # produce", so the two catalogs must agree on which models emit what.
    bad_instr = []
    for mid, m in ui_models.items():
        w = sorted(set(worker.get(mid, {}).get("instrumentTargets", [])))
        if w != m["instrumentTargets"]:
            bad_instr.append(f"{mid}: worker={w or '-'} ui={m['instrumentTargets'] or '-'}")
    if bad_instr:
        check(FAIL, "instruments: tags differ between catalogs", "; ".join(bad_instr))
    else:
        tagged = sum(1 for m in ui_models.values() if m["instrumentTargets"])
        check(OK, "instruments: tags match in both files", f"{tagged} tagged")

    # An instrument scene with no instrument-capable model at all would render
    # an empty grid with nothing to explain it.
    bad_scene = []
    for scene, meta in scenes.items():
        if not meta["instrument"]:
            continue
        if not any(m["instrumentTargets"] for m in ui_models.values()):
            bad_scene.append(f"{scene}: no model declares instrumentTargets")
    if bad_scene:
        check(FAIL, "instruments: scene has no usable models", "; ".join(bad_scene))
    else:
        inst = [s for s, m in scenes.items() if m["instrument"]]
        check(OK, "instruments: every instrument scene has models", f"{len(inst)} scenes")

    # 4c. repair capability parity ----------------------------------------
    bad_repair = []
    for mid, m in ui_models.items():
        w = worker.get(mid, {}).get("repair")
        if w != m["repair"]:
            bad_repair.append(f"{mid}: worker={w} ui={m['repair']}")
    if bad_repair:
        check(FAIL, "repair: capabilities differ between catalogs", "; ".join(bad_repair))
    else:
        tagged = sum(1 for m in ui_models.values() if m["repair"])
        check(OK, "repair: capabilities match in both files", f"{tagged} declared")

    # A declared repair capability is a promise. Without a primaryStem the
    # workflow cannot tell which output is the repaired one and would have to
    # guess, so that combination is a catalog bug rather than a warning.
    incomplete = [
        mid for mid, m in ui_models.items()
        if m["repair"] and not (m["repair"].get("primaryStem") and m["repair"].get("categories"))
    ]
    if incomplete:
        check(FAIL, "repair: capability missing primaryStem/categories", ", ".join(sorted(incomplete)))
    else:
        check(OK, "repair: every capability names a primaryStem and category")

    # 5. UI-only ids are ensembles ----------------------------------------
    stray = sorted(i for i in ui_only if not ui_models[i]["ensemble"])
    if stray:
        check(FAIL, "ensembles: UI-only id is not marked ensemble:true", ", ".join(stray))
    else:
        check(OK, "ensembles: UI-only ids all marked ensemble:true")

    # --- report -----------------------------------------------------------
    failures = [r for r in rows if r[0] == FAIL]
    warnings = [r for r in rows if r[0] == WARN]

    if args.json:
        print(
            json.dumps(
                {
                    "ok": not failures,
                    "checks": [
                        {"level": lv, "name": n, "detail": d} for lv, n, d in rows
                    ],
                },
                indent=2,
            )
        )
    else:
        width = max(len(n) for _, n, _ in rows)
        for level, name, detail in rows:
            mark = {OK: "✓", WARN: "!", FAIL: "✗"}[level]
            line = f"{mark} {name.ljust(width)}"
            if detail:
                line += f"  {detail}"
            print(line)
        print()
        if failures:
            print(f"FAILED — {len(failures)} check(s) failed, {len(warnings)} warning(s)")
        else:
            print(f"OK — {len(rows)} checks passed")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())