#!/usr/bin/env python3
"""
Pin Hugging Face provenance into api/models.json.

For every catalog entry with a `download` spec this records, per file:

    repo      the HF repository the bytes come from
    revision  the resolved COMMIT SHA (never the moving `main` branch)
    remote    the path within that repo
    dest      the filename it is stored under locally
    size      exact byte count
    sha256    hash of the exact bytes

Why this matters: `main` is mutable. A model that loads today can 404 or, worse,
silently change bytes tomorrow, and `model_manager._verify()` then has nothing to
compare against. Pinning the commit makes a download reproducible, and the hash
makes it *verifiable* — `_verify()` already enforces both fields once they are
populated; this script is what populates them.

Files already installed locally are hashed in place (free). The rest are
streamed once into a temp file, hashed, and deleted.

Usage:
    python3 scripts/pin-provenance.py --dry-run   # report, download nothing
    python3 scripts/pin-provenance.py             # pin everything missing
    python3 scripts/pin-provenance.py --only mbr_guitar_becruily
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "api" / "models.json"
MODEL_STORE = ROOT / "models"
HF = "https://huggingface.co"
CHUNK = 1 << 20


def head_size(url: str) -> int:
    """Exact content length via a ranged GET.

    A plain HEAD is unreliable here: HF redirects to a CDN that answers HEAD
    with 405 for some paths. Requesting a single byte and reading
    Content-Range's total is the portable way to get the real size.
    """
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        cr = r.headers.get("Content-Range", "")
        if "/" in cr:
            return int(cr.rsplit("/", 1)[1])
        return int(r.headers.get("Content-Length", 0))


def resolve_revision(repo: str) -> str | None:
    """Current commit SHA of a repo's main branch."""
    url = f"{HF}/api/models/{repo}/revision/main"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return json.loads(r.read()).get("sha")
    except (urllib.error.URLError, json.JSONDecodeError, KeyError):
        return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def download_and_hash(url: str) -> tuple[int, str]:
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        h = hashlib.sha256()
        total = 0
        req = urllib.request.Request(url, headers={"User-Agent": "uvr-local/1.0"})
        with urllib.request.urlopen(req, timeout=1800) as r, tmp as out:
            while True:
                chunk = r.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                total += len(chunk)
        return total, h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only, download nothing")
    ap.add_argument("--only", action="append", help="restrict to these model ids")
    ap.add_argument("--force", action="store_true", help="re-pin even if already pinned")
    args = ap.parse_args()

    catalog = json.loads(CATALOG.read_text())
    downloads = {k: v for k, v in catalog.items() if v.get("download")}
    if args.only:
        downloads = {k: v for k, v in downloads.items() if k in set(args.only)}

    changed = 0
    to_fetch: list[tuple[str, dict, dict]] = []

    for mid, entry in downloads.items():
        spec = entry["download"]
        rev = spec.get("revision")
        pinned = rev and rev != "main"
        files = spec.get("files", [])
        complete = all(f.get("sha256") and f.get("size") for f in files)
        if complete and pinned and not args.force:
            print(f"  = {mid:28} already pinned @ {rev[:12]}")
            continue

        if not pinned or args.force:
            new_rev = resolve_revision(spec["repo"])
            if new_rev and (new_rev != rev):
                print(f"  ~ {mid:28} revision {rev or 'unset'} -> {new_rev[:12]}")
                spec["revision"] = new_rev
                changed += 1
            elif not new_rev:
                print(f"  ! {mid:28} could not resolve revision for {spec['repo']}")

        for f in files:
            if f.get("sha256") and f.get("size") and not args.force:
                continue
            to_fetch.append((mid, spec, f))

    if args.dry_run:
        total = 0
        for mid, spec, f in to_fetch:
            dest = f.get("dest") or Path(f["remote"]).name
            local = MODEL_STORE / mid / dest
            if local.exists():
                print(f"  ~ {mid:28} {dest:34} local {local.stat().st_size/1e6:8.1f} MB")
            else:
                try:
                    size = head_size(f"{HF}/{spec['repo']}/resolve/{spec.get('revision','main')}/{f['remote']}")
                except Exception as exc:  # noqa: BLE001 - report, don't abort the sweep
                    print(f"  ! {mid:28} {dest:34} size unavailable ({exc})")
                    continue
                total += size
                print(f"  ~ {mid:28} {dest:34} remote {size/1e6:8.1f} MB  (needs download)")
        print(f"\ndry run: {len(to_fetch)} file(s) unpinned, {total/1e9:.2f} GB to fetch")
        return 0

    for mid, spec, f in to_fetch:
        dest = f.get("dest") or Path(f["remote"]).name
        local = MODEL_STORE / mid / dest
        if local.exists():
            size, digest = local.stat().st_size, sha256_file(local)
            origin = "local"
        else:
            url = f"{HF}/{spec['repo']}/resolve/{spec['revision']}/{f['remote']}"
            try:
                size, digest = download_and_hash(url)
            except (urllib.error.URLError, OSError) as exc:
                print(f"  ! {mid:28} {dest:34} {exc}")
                continue
            origin = "remote"
        f["size"], f["sha256"] = size, digest
        changed += 1
        print(f"  + {mid:28} {dest:34} {size/1e6:8.1f} MB  {digest[:16]}… ({origin})")

    if changed:
        CATALOG.write_text(json.dumps(catalog, indent=2) + "\n")
    print(f"\npinned {changed} change(s) into {CATALOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())