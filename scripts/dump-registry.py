#!/usr/bin/env python3
"""
Snapshot audio-separator's model registry to a local JSON file.

The registry is the verified, downloadable source for catalog work: every entry
is a file audio-separator knows how to fetch AND configure itself. Enumerating
it requires importing `Separator`, which drags in torch/onnxruntime and spews
CUDA loader warnings on this box, so the snapshot means later waves can look
models up without that cost.

Run:  cd api && .venv/bin/python ../scripts/dump-registry.py
Out:  scripts/registry-snapshot.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scripts" / "registry-snapshot.json"

# Noise Separator emits on this machine; the call still succeeds.
_NOISE = re.compile(
    r"(Failed to load lib|Please follow https://onnxruntime|separator - |^INFO:)"
)


def main() -> int:
    sys.path.insert(0, str(ROOT / "api"))
    from audio_separator.separator import Separator

    sep = Separator()
    raw = sep.get_simplified_model_list()

    # get_simplified_model_list() returns a dict keyed by FILENAME. Guard
    # explicitly: list_supported_model_files() returns just 4 type strings
    # ('Demucs','MDX','MDXC','VR') and silently using that instead would
    # produce a snapshot of nothing useful.
    if not isinstance(raw, dict):
        print(f"error: expected a dict, got {type(raw).__name__}", file=sys.stderr)
        return 1

    entries = {}
    for key, value in raw.items():
        meta = value if isinstance(value, dict) else {}
        entries[str(key)] = {
            "type": meta.get("type") or meta.get("model_type") or "",
            "name": meta.get("name") or meta.get("model_name") or str(key),
            "is_uvr_vip": bool(meta.get("is_uvr_vip", False)),
        }

    families: dict[str, int] = {}
    for filename in entries:
        if filename.endswith((".pth", ".ckpt", ".onnx", ".yaml")):
            base = filename.rsplit(".", 1)[0]
        else:
            base = filename
        if re.search(r"roformer|hyperace", base, re.I):
            key = "roformer"
        elif re.search(r"mel_?band", base, re.I):
            key = "melband"
        elif re.search(r"uvr|hp-", base, re.I):
            key = "uvr"
        elif re.search(r"demucs", base, re.I):
            key = "demucs"
        elif re.search(r"mdx", base, re.I):
            key = "mdx"
        else:
            key = "other"
        families[key] = families.get(key, 0) + 1

    payload = {
        "source": "audio_separator.separator.Separator.get_simplified_model_list()",
        "audio_separator_version": getattr(
            __import__("audio_separator"), "__version__", "unknown"
        ),
        "count": len(entries),
        "families": dict(sorted(families.items(), key=lambda kv: -kv[1])),
        "models": dict(sorted(entries.items(), key=lambda kv: kv[0].lower())),
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} — {len(entries)} entries")
    for fam, n in payload["families"].items():
        print(f"  {fam:10s} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())