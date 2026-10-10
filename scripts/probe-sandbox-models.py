#!/usr/bin/env python3
"""
Probe NON-registry models (arbitrary ckpt + config) through the REAL worker path.

Why this exists: `probe-registry-model.py` can only load filenames that exist in
audio-separator's registry. Most of the interesting candidates (Metal, guitar,
BVE, the second Duality config) are NOT in it — they live in a Hugging Face
mirror and are loaded via our `download.files` mechanism instead.

Rather than write a second loader that duplicates backend.py's config-alias and
RoFormer-detection logic, this builds a SANDBOX catalogue and points a real
worker at it via `MODEL_CATALOG`. Whatever passes here is therefore proven
through the exact code path production uses.

Nothing here touches api/models.json or web/src/lib/models.ts. Winners are
promoted separately by scripts/add-verified-models.py.

Usage:
  python3 scripts/probe-sandbox-models.py --build
  ./scripts/restart-worker.sh      # picks up MODEL_CATALOG from the sandbox env
  python3 scripts/probe-sandbox-models.py --report <jobId> [<jobId> ...]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = Path("/tmp/uvr-sandbox")
SANDBOX_MODELS = SANDBOX / "models.json"
SANDBOX_STORE = SANDBOX / "models"

HF = "https://huggingface.co/Politrees/UVR_resources/resolve/main/models/Roformer/MelBand"

# Each entry mirrors what a shipped `download.files` catalogue entry looks like.
# `repo` is the HF repo id; `files` maps destination name -> repo-relative path.
CANDIDATES = [
    {
        "id": "sb_metal_mesk",
        "name": "Metal Inst (MESK)",
        "arch": "MelBand-RoFormer",
        "target": "instrumental",
        "trial_name": "Mel-Band RoFormer Inst Metal (MESK)",
        "files": {
            "melband_roformer_inst_metal_prev_by_mesk.ckpt":
                f"{HF}/melband_roformer_inst_metal_prev_by_mesk.ckpt",
            "config_melband_roformer_inst_metal_prev_by_mesk.yaml":
                f"{HF}/config_melband_roformer_inst_metal_prev_by_mesk.yaml",
        },
    },
    {
        "id": "sb_guitar_becruily",
        "name": "Guitar (becruily)",
        "arch": "MelBand-RoFormer",
        "target": "instrumental",
        "trial_name": "Mel-Band RoFormer Guitar",
        "files": {
            "melband_roformer_guitar_becruily.ckpt":
                f"{HF}/melband_roformer_guitar_becruily.ckpt",
            "config_melband_roformer_guitar_becruily.yaml":
                f"{HF}/config_melband_roformer_guitar_becruily.yaml",
        },
    },
    {
        "id": "sb_bve_gonza",
        "name": "BVE by Gonza",
        "arch": "MelBand-RoFormer",
        "target": "vocals",
        "trial_name": "Mel-Band RoFormer BVE",
        "files": {
            "model_MelBand-Roformer_BVE_by-Gonza.ckpt":
                f"{HF}/model_MelBand-Roformer_BVE_by-Gonza.ckpt",
            "config_MelBand-Roformer_BVE_by-Gonza.yaml":
                f"{HF}/config_MelBand-Roformer_BVE_by-Gonza.yaml",
        },
    },
    {
        "id": "sb_duality_aname",
        "name": "Duality v1 (Aname)",
        "arch": "MelBand-RoFormer",
        "target": "dual",
        "trial_name": "Mel-Band RoFormer Duality v1 (Aname)",
        "files": {
            "model_MelBand-Roformer_Duality_v1_by-Aname.ckpt":
                f"{HF}/model_MelBand-Roformer_Duality_v1_by-Aname.ckpt",
            "config_MelBand-Roformer_Duality_v1_by-Aname.yaml":
                f"{HF}/config_MelBand-Roformer_Duality_v1_by-Aname.yaml",
        },
    },
]


def head(url: str) -> tuple[int, int]:
    """(status, content-length) for a HEAD request, without downloading."""
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, int(r.headers.get("Content-Length") or 0)
    except urllib.error.HTTPError as exc:
        # HF serves large files via a 302 to a CDN; a 404 is a real miss.
        return exc.code, 0
    except Exception:  # noqa: BLE001
        return 0, 0


def build() -> int:
    SANDBOX_STORE.mkdir(parents=True, exist_ok=True)
    cat: dict[str, dict] = {}

    print("verifying every source URL exists before writing the catalogue:\n")
    bad = 0
    for c in CANDIDATES:
        print(f"  {c['id']}  ({c['trial_name']})")
        for dest, url in c["files"].items():
            status, length = head(url)
            ok = status == 200
            bad += 0 if ok else 1
            mb = length / 1048576 if length else 0
            print(f"    {'OK ' if ok else 'MISSING'} {status} {mb:7.1f} MB  {dest}")
        cat[c["id"]] = {
            "download": {
                "repo": "Politrees/UVR_resources",
                "repoType": "hf",
                "revision": "main",
                "files": [
                    {
                        # model_manager builds the URL itself from repo+remote,
                        # so it needs the repo-relative path, not a full URL.
                        "remote": f"models/Roformer/MelBand/{url.split('/MelBand/')[-1]}",
                        "dest": dest,
                        "size": 0,
                    }
                    for dest, url in c["files"].items()
                ],
            },
            "name": c["trial_name"],
            "arch": c["arch"],
            "target": c["target"],
            "tags": [],
            "sizeMB": 0,
            "source": "Hugging Face Politrees/UVR_resources (trial)",
            "sdr": None,
            "model_type": "vocal_models",
            "license": "UNVERIFIED — check before shipping",
        }

    SANDBOX_MODELS.write_text(json.dumps(cat, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {SANDBOX_MODELS} with {len(cat)} trial entries")
    if bad:
        print(f"!! {bad} source URL(s) unreachable", file=sys.stderr)
        return 2
    print("\nrestart the worker against the sandbox:")
    print("  MODEL_CATALOG=/tmp/uvr-sandbox/models.json \\")
    print("  MODEL_STORE=/tmp/uvr-sandbox/models \\")
    print("  ./scripts/restart-worker.sh")
    return 0


def report(job_ids: list[str]) -> int:
    import urllib.request

    for jid in job_ids:
        with urllib.request.urlopen(
            f"http://localhost:8000/api/jobs/{jid}", timeout=15
        ) as r:
            d = json.load(r)
        print(f"\njob {jid}  status={d['status']}  model={d['modelId']}")
        if d.get("error"):
            print(f"  ERROR: {d['error'][:300]}")
            continue
        for s in d.get("resultStems") or []:
            print(f"  stem: {s['name']}  ({s['sizeBytes']} bytes)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--report", nargs="+", metavar="JOBID")
    args = ap.parse_args()
    if args.build:
        return build()
    if args.report:
        return report(args.report)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())