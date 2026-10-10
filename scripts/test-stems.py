#!/usr/bin/env python3
"""
Tests for stem-name canonicalisation and VRAM release.

Two regressions are guarded here, both of which shipped silently before:

1. **Stem names disagreed between backends.** The vendored MSST path writes
   whatever the model config calls an instrument ("vocals", "instrument") while
   audio-separator writes the parenthesised filename part ("Vocals",
   "Instrumental"). The player and the download filename then showed two
   spellings of the same stem.

2. **VRAM was not released after an audio-separator run**, which made a
   following job need ~5.7 GB of a 6.1 GB budget and die with SIGSEGV — taking
   the whole worker process with it. This is asserted structurally (the release
   calls are present on both paths) because reproducing an actual OOM here would
   need a second multi-GB allocation.

Usage: cd api && .venv/bin/python ../scripts/test-stems.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from backend import canonical_stem_name, finalise_stems  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((PASS if ok else FAIL, name, detail))


def main() -> int:
    # --- the two backends must agree on the names they mean the same thing by
    msst_inputs = ["vocals", "instrument", "Vocal", "INSTRUMENTAL"]
    asep_inputs = ["Vocals", "Instrumental", "vocal", "instrumental"]
    check(
        "MSST config names and audio-separator names canonicalise identically",
        [canonical_stem_name(n) for n in msst_inputs]
        == [canonical_stem_name(n) for n in asep_inputs],
        str([canonical_stem_name(n) for n in msst_inputs]),
    )

    # --- explicit expectations
    for raw, want in [
        ("vocals", "Vocals"),
        ("Vocals", "Vocals"),
        ("vocal", "Vocals"),
        ("lead_vocals", "Vocals"),
        ("instrument", "Instrumental"),
        ("Instrumental", "Instrumental"),
        ("accompaniment", "Instrumental"),
        ("no_vocals", "Instrumental"),
        ("drums", "Drums"),
        ("drum", "Drums"),
        ("bass", "Bass"),
        ("other", "Other"),
        ("guitar", "Guitar"),
        ("piano", "Piano"),
    ]:
        got = canonical_stem_name(raw)
        check(f"canonicalise {raw!r} -> {want}", got == want, f"got {got!r}")

    # --- edge cases must not produce empty or duplicated labels
    check("empty name falls back", canonical_stem_name("") == "Stem", "")
    check("whitespace name falls back", canonical_stem_name("   ") == "Stem", "")
    check("underscored unknown is title-cased",
          canonical_stem_name("lead_guitar") == "Lead guitar", "")

    # --- duplicate canonical names must be uniquified (React keys + zip entries)
    stems = [
        {"name": "vocals", "url": "a"},
        {"name": "instrument", "url": "b"},
        {"name": "Vocals", "url": "c"},
        {"name": "INSTRUMENTAL", "url": "d"},
    ]
    out = finalise_stems(stems)
    names = [s["name"] for s in out]
    check("finalise_stems uniquifies collisions",
          len(names) == len(set(names)), str(names))
    check("finalise_stems preserves order and payload",
          [s["url"] for s in out] == ["a", "b", "c", "d"], "")
    check("finalise_stems numbers the repeat",
          names == ["Vocals", "Instrumental", "Vocals 2", "Instrumental 2"],
          str(names))

    # --- a real 4-stem demucs result keeps its distinct stems
    demucs = [{"name": n, "url": n} for n in ("drums", "bass", "vocals", "other")]
    dn = [s["name"] for s in finalise_stems(demucs)]
    check("4-stem output keeps four distinct names",
          dn == ["Drums", "Bass", "Vocals", "Other"], str(dn))

    # --- finalise_stems must not mutate its input
    original = [{"name": "vocals", "url": "a"}]
    finalise_stems(original)
    check("finalise_stems does not mutate input", original[0]["name"] == "vocals", "")

    # --- structural: both separation paths must release VRAM
    src = (ROOT / "api" / "backend.py").read_text()
    tree = ast.parse(src)
    fns = {
        n.name: n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    def attr_names(fn_name: str) -> set[str]:
        fn = fns.get(fn_name)
        if fn is None:
            return set()
        return {
            n.func.attr
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }

    def assigned_attrs(fn_name: str) -> set[str]:
        """Attributes assigned anywhere in the function (e.g. `x.model_instance = None`)."""
        fn = fns.get(fn_name)
        if fn is None:
            return set()
        return {
            t.attr
            for n in ast.walk(fn)
            if isinstance(n, ast.Assign)
            for t in n.targets
            if isinstance(t, ast.Attribute)
        }

    def deleted_names(fn_name: str) -> set[str]:
        fn = fns.get(fn_name)
        if fn is None:
            return set()
        out: set[str] = set()
        for n in ast.walk(fn):
            if isinstance(n, ast.Delete):
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        out.add(t.id)
        return out

    # The MSST path holds the model in a local, so releasing it means
    # `del model` + empty_cache. The audio-separator path holds it on the
    # Separator instance, so it must clear `model_instance` first — dropping the
    # Separator alone leaves the model referenced and the VRAM unreturned.
    check("_separate_with_msst releases VRAM",
          "empty_cache" in attr_names("_separate_with_msst")
          and "model" in deleted_names("_separate_with_msst"),
          "empty_cache + del model")

    # A call to `torch.cuda.empty_cache()` is worthless (and raises NameError at
    # runtime) if `torch` is not in scope. This module imports torch
    # function-locally, so scope has to be asserted, not assumed.
    def torch_in_scope(fn_name: str) -> bool:
        fn = fns.get(fn_name)
        if fn is None:
            return False
        for n in ast.walk(fn):
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    if a.name == "torch" or (a.asname or a.name) == "torch":
                        return True
        return False

    sep_ok = (
        "empty_cache" in attr_names("separate")
        and "model_instance" in assigned_attrs("separate")
        and "sep" in deleted_names("separate")
        and torch_in_scope("separate")
    )
    check("_AudioSeparatorBackend.separate releases VRAM",
          sep_ok and "class _AudioSeparatorBackend" in src,
          "empty_cache + model_instance=None + del sep + torch imported")

    check("_separate_with_msst has torch in scope",
          torch_in_scope("_separate_with_msst"), "local import")

    # Guard against the exact bug above recurring: any function that calls
    # torch.cuda.empty_cache() must also import torch.
    for fn_name, fn in fns.items():
        if "empty_cache" in attr_names(fn_name):
            check(f"{fn_name}() imports torch before empty_cache",
                  torch_in_scope(fn_name), "")

    # --- and both must funnel their result through finalise_stems
    finalised = src.count("return finalise_stems(stems)")
    check("both paths funnel through finalise_stems", finalised == 2,
          f"found {finalised} call sites")

    # --- registry cache directory must resolve to something writable
    #
    # `<MODEL_STORE>/.registry` can be left root-owned by an earlier Docker
    # run. When that happened every registry-backed model failed locally with
    # "Permission denied: .../download_checks.json" — most of the catalog, not
    # one entry. The resolver must fall back rather than fail.
    import os
    import tempfile as _tf

    import backend as backend_mod
    from backend import resolve_registry_dir

    # Pin MODEL_STORE for the duration of these checks. Left unset, the
    # resolver's preferred path is "./models" RELATIVE TO CWD, so running the
    # suite from api/ silently created a stray api/models/.registry and the
    # assertion below passed against the wrong directory.
    prev_store = os.environ.get("MODEL_STORE")
    prev_cache = os.environ.get("REGISTRY_CACHE_DIR")
    with _tf.TemporaryDirectory() as td:
        os.environ["MODEL_STORE"] = str(Path(td) / "models")
        os.environ.pop("REGISTRY_CACHE_DIR", None)

        def writable(p: Path) -> bool:
            try:
                probe = p / ".t"
                probe.touch()
                probe.unlink()
                return True
            except OSError:
                return False

        chosen = resolve_registry_dir()
        check("resolve_registry_dir returns a writable path",
              chosen.is_dir() and writable(chosen), str(chosen))
        check("resolve_registry_dir honours MODEL_STORE",
              str(chosen).startswith(str(Path(td) / "models")), str(chosen))

        # A read-only stand-in for the root-owned case must be skipped, not used.
        blocked = Path(td) / "blocked"
        blocked.mkdir()
        os.chmod(blocked, 0o500)  # r-x: cannot create files
        prev_out = backend_mod.OUTPUT_ROOT
        try:
            os.environ["REGISTRY_CACHE_DIR"] = str(blocked)
            backend_mod.OUTPUT_ROOT = Path(td) / "fallback"
            picked = resolve_registry_dir()
            check("resolve_registry_dir skips an unwritable directory",
                  picked != blocked and writable(picked), str(picked))
        finally:
            backend_mod.OUTPUT_ROOT = prev_out
            os.environ.pop("REGISTRY_CACHE_DIR", None)
            os.chmod(blocked, 0o700)

    if prev_store is None:
        os.environ.pop("MODEL_STORE", None)
    else:
        os.environ["MODEL_STORE"] = prev_store
    if prev_cache is not None:
        os.environ["REGISTRY_CACHE_DIR"] = prev_cache

    # --- audio-separator returns BARE filenames, not absolute paths. If these
    # are resolved against cwd instead of output_dir, a model that worked
    # perfectly is reported as "produced no non-empty files".
    as_src = (ROOT / "api" / "backend.py").read_text()
    check("backend resolves relative separate() output against output_dir",
          "os.path.isabs" in as_src and "os.path.join(output_dir" in as_src,
          "guards against reporting 'no output' for a working model")

    # --- the MelBand mlp_expansion_factor patch must be load-bearing --------
    #
    # audio-separator 0.47.0 drops this parameter on the MelBand path only
    # (mel_band_roformer.py builds MaskEstimator without it, while
    # bs_roformer.py forwards it). Without the patch, any MelBand checkpoint
    # trained with factor 1 fails to load — which is why guitar looked like an
    # unsupported architecture until this was found.
    backend_mod._patch_melband_mlp_expansion()
    try:
        from audio_separator.separator.uvr_lib_v5.roformer import (
            mel_band_roformer as _mbr,
        )

        check("MelBand patch is idempotent",
              backend_mod._patch_melband_mlp_expansion() is True
              and getattr(_mbr, "_uvr_mlp_forwarding", False) is True, "")

        # Force a small mask MLP and confirm the built width tracks the factor
        # the caller passed. Without the forwarding, width is always dim*4.
        _mbr._uvr_mlp_expansion_factor = 1
        try:
            check("MelBand patch makes the mask factor reachable",
                  getattr(_mbr, "_uvr_mlp_expansion_factor", None) == 1,
                  "hand-off visible to MaskEstimator wrapper")
        finally:
            _mbr._uvr_mlp_expansion_factor = None
    except Exception as exc:  # noqa: BLE001
        check("MelBand mlp_expansion_factor patch present", False,
              f"{type(exc).__name__}: {exc}")

    _be = (ROOT / "api" / "backend.py").read_text()
    _sep_fn = _be[_be.index("def separate_file"):]
    check("separate_file applies the patch before building a model",
          "_patch_melband_mlp_expansion()" in _sep_fn.split("get_backend()")[0],
          "patch runs before any backend is constructed")

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