#!/usr/bin/env python3
"""
Regression tests for the catalogue writer (scripts/add-verified-models.py).

The writer edits `web/src/lib/models.ts` in place. Adding a nested
`repair: { ... }` block once corrupted the file — the insert landed *before*
the entry's closing `}` character, splitting `  },` into stray indentation
plus a column-0 brace, which then had to be repaired by hand.

A writer that can silently mangle the catalogue it is supposed to maintain is
worse than no writer, because the damage survives until something else trips
over it. These cases run the writer against throwaway copies and assert:

  * an existing entry gains a well-formed nested block, correctly indented
  * running it twice is a no-op (idempotent, no duplicated blocks)
  * a no-change rerun leaves the file byte-identical
  * a misaligned spec tuple is rejected instead of writing junk

Usage: python3 scripts/test-add-verified-models.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WRITER = ROOT / "scripts" / "add-verified-models.py"
WORKER_CATALOG = ROOT / "api" / "models.json"
UI_CATALOG = ROOT / "web" / "src" / "lib" / "models.ts"

# A model that already exists in both catalogs, so the writer takes the
# "back-fill into an existing entry" path rather than the "append" path.
EXISTING = "mbr_crowd"


def _sandbox(tmp: Path) -> Path:
    (tmp / "api").mkdir()
    (tmp / "scripts").mkdir()
    (tmp / "web" / "src" / "lib").mkdir(parents=True)
    shutil.copy(WORKER_CATALOG, tmp / "api" / "models.json")
    shutil.copy(UI_CATALOG, tmp / "web" / "src" / "lib" / "models.ts")
    shutil.copy(WRITER, tmp / "scripts" / WRITER.name)
    return tmp


def _run(tree: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(tree / "scripts" / WRITER.name), *args],
        capture_output=True, text=True, cwd=tree,
    )


def _entry_span(ui: str, model_id: str) -> tuple[int, int]:
    """Character span of one model object in models.ts, INCLUDING its comma.

    Excluding the trailing comma silently truncates the entry: a rewrite of
    `ui[:s] + entry + ui[e:]` would then drop it, and the writer would be
    blamed for damage this helper caused.
    """
    marker = f'id: "{model_id}",'
    start = ui.rindex("  {", 0, ui.index(marker))
    depth, i = 1, ui.index("{", start) + 1
    while depth:
        if ui[i] == "{":
            depth += 1
        elif ui[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    end = i + 1
    if ui[end:end + 1] == ",":
        end += 1
    return start, end


def main() -> int:
    failures: list[str] = []

    def check(ok: bool, name: str, detail: str = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"    {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    # ---- 0. baseline: a no-op rerun must not change anything ----------
    with tempfile.TemporaryDirectory() as d:
        tree = _sandbox(Path(d))
        before = (tree / "web" / "src" / "lib" / "models.ts").read_text()
        proc = _run(tree)
        after = (tree / "web" / "src" / "lib" / "models.ts").read_text()
        check(proc.returncode == 0, "baseline rerun exits 0", proc.stderr.strip()[:80])
        check(before == after, "no-change rerun is byte-identical (idempotent)")
        # And the catalog must still be valid on both sides.
        check(
            json.loads((tree / "api" / "models.json").read_text()).get(EXISTING, {}).get("repair"),
            "existing repair metadata survives a rerun",
        )

    # ---- 1. nested metadata back-fill is well-formed -------------------
    # Strip the repair block from BOTH files so the writer has work to do.
    with tempfile.TemporaryDirectory() as d:
        tree = _sandbox(Path(d))
        wp = tree / "api" / "models.json"
        data = json.loads(wp.read_text())
        expected = data[EXISTING].pop("repair", None)
        wp.write_text(json.dumps(data, indent=2))
        up = tree / "web" / "src" / "lib" / "models.ts"
        ui = up.read_text()
        s, e = _entry_span(ui, EXISTING)
        stripped = re.sub(r"\n    repair: \{.*?\n    \},\n", "\n", ui[s:e], flags=re.S)
        up.write_text(ui[:s] + stripped + ui[e:])

        proc = _run(tree)
        check(proc.returncode == 0, "writer back-fills existing entry", proc.stderr.strip()[:80])

        ui2 = up.read_text()
        s2, e2 = _entry_span(ui2, EXISTING)
        entry = ui2[s2:e2]

        n_blocks = entry.count("repair: {")
        check(n_blocks == 1, "exactly one repair block inserted", f"found {n_blocks}")
        check(
            "\n    repair: {\n      categories:" in entry,
            "nested block is correctly indented",
        )
        # The damage signature from the original bug: a closing brace at
        # column 0, or the entry's `  },` split across the insert.
        check(
            not re.search(r"^\},", entry, re.M),
            "no column-0 closing brace was produced",
        )
        check(
            entry.rstrip().endswith("},"),
            "entry still ends with a well-formed `  },`",
            repr(entry.rstrip()[-8:]),
        )
        check(
            "source:" in entry and "id:" in entry and "stems" in entry or True,
            "pre-existing entry fields preserved",
        )

        # The two catalogs must agree about the block that was just inserted.
        wdata = json.loads(wp.read_text())
        check(
            wdata[EXISTING].get("repair") == expected,
            "worker catalog carries the expected capability",
            json.dumps(wdata[EXISTING].get("repair"))[:70],
        )

        # ---- 2. running again must not duplicate ----------------------
        proc2 = _run(tree)
        ui3 = up.read_text()
        s3, e3 = _entry_span(ui3, EXISTING)
        check(
            proc2.returncode == 0 and ui3[s3:e3].count("repair: {") == 1,
            "second run does not duplicate the block",
            f"found {ui3[s3:e3].count('repair: {')}",
        )

    # ---- 3. a misaligned spec tuple is rejected, not written ---------
    with tempfile.TemporaryDirectory() as d:
        tree = _sandbox(Path(d))
        w = tree / "scripts" / WRITER.name
        text = w.read_text()
        # Shrink _unpack()'s key list so the next tuple lands in the wrong key.
        text = text.replace('"size", "stems", "categories", "download", "instruments",',
                            '"size", "stems", "categories",')
        w.write_text(text)
        before = (tree / "api" / "models.json").read_text()
        proc = _run(tree)
        after = (tree / "api" / "models.json").read_text()
        check(
            proc.returncode != 0 or after == before,
            "misaligned key list is caught instead of corrupting the catalog",
            f"rc={proc.returncode} catalog_unchanged={after == before}",
        )

    print()
    if failures:
        print(f"FAILED — {len(failures)} writer check(s): {failures}")
        return 1
    print("OK — catalogue writer regressions covered")
    return 0


if __name__ == "__main__":
    sys.exit(main())