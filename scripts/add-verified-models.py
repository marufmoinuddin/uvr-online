#!/usr/bin/env python3
"""
Add the probe-verified registry models to BOTH catalogs.

Writes `api/models.json` and the matching entries into
`web/src/lib/models.ts`. Two files, always together — a model or an
`unsupported` flag in only one has broken the picker three times.

Only models that PROBED CLEAN may be listed here. The two that failed to load
(`SystemExit: 1`, a state_dict mismatch) are recorded as `unsupported` with the
reason instead, so they are hidden from the picker rather than offered as a
dead end.

Specs are POSITIONAL tuples aligned to `_unpack()`'s key list — a tuple one
field short writes its last value into the wrong key and corrupts the catalogue.
`worker_entry()` type-checks `download`/`instruments` and exits on a mismatch.

Usage: python3 scripts/add-verified-models.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / "api" / "models.json"
UI = ROOT / "web" / "src" / "lib" / "models.ts"

# --- probe results (scripts/probe-registry-model.py, 2026-10-10) --------------
#
# `probed: True` means the checkpoint loaded here AND produced decodable stems
# from a real 20s music clip. `probed: False` with a reason means it was tried
# and could not be loaded, so it must be `unsupported`, never offered.
VERIFIED = [
    # (id, display name, short name, registry filename, arch, target, trait, sizeMB)
    ("uvr_2hp", "2 HP UVR", "2 HP UVR", "2_HP-UVR.pth", "VR", "dual",
     "Full band", 121),
    ("bs_roformer_voc_gabox", "BS-RoFormer Vocals (Gabox)", "Vocals Gabox",
     "bs_roformer_vocals_gabox.ckpt", "BS-RoFormer", "vocals", "Fuller sound", 610),
    ("mbr_inst_v1e_plus", "Mel-Band RoFormer Inst V1E Plus", "Inst V1E Plus",
     "melband_roformer_inst_v1e_plus.ckpt", "MelBand-RoFormer", "instrumental",
     "Low bleed", 871),
    ("mbr_inst_v2", "Mel-Band RoFormer Inst V2", "Inst V2",
     "melband_roformer_inst_v2.ckpt", "MelBand-RoFormer", "instrumental",
     "Clean boundary", 1502),
    ("mbr_inst_3_gabox", "Mel-Band RoFormer Inst 3 (Gabox)", "Inst 3 Gabox",
     "mel_band_roformer_instrumental_3_gabox.ckpt", "MelBand-RoFormer",
     "instrumental", "Balanced", 871),
    ("mbr_fullness_v4", "Mel-Band RoFormer Fullness V4", "Fullness V4",
     "mel_band_roformer_instrumental_fullness_v4_gabox.ckpt",
     "MelBand-RoFormer", "instrumental", "Fuller sound", 871),
    ("mbr_fullness_noise_v4", "Mel-Band RoFormer Fullness Noise V4",
     "Fullness Noise V4",
     "mel_band_roformer_instrumental_fullness_noise_v4_gabox.ckpt",
     "MelBand-RoFormer", "instrumental", "Noise reduction", 871),
    ("mbr_inst_fv8", "Mel-Band RoFormer Inst FV8", "Inst FV8",
     "mel_band_roformer_instrumental_fv8_gabox.ckpt", "MelBand-RoFormer",
     "instrumental", "Dual stems", 871),
    ("mbr_inst_fvx", "Mel-Band RoFormer Inst FVX", "Inst FVX",
     "mel_band_roformer_instrumental_fvx_gabox.ckpt", "MelBand-RoFormer",
     "instrumental", "Detailed split", 871),
    ("mbr_instv8", "Mel-Band RoFormer InstV8", "InstV8",
     "mel_band_roformer_instrumental_instv8_gabox.ckpt", "MelBand-RoFormer",
     "instrumental", "Stable stems", 871),
    ("mbr_instv8n", "Mel-Band RoFormer InstV8N", "InstV8N",
     "mel_band_roformer_instrumental_instv8n_gabox.ckpt", "MelBand-RoFormer",
     "instrumental", "Breaths & tails", 871),
    ("mdx23c_instvoc_hq_2", "MDX23C InstVoc HQ 2", "MDX23C HQ 2",
     "MDX23C-8KFFT-InstVoc_HQ_2.ckpt", "MDX23C", "dual", "High quality", 428),
    ("mdx23c_d1581", "MDX23C D1581", "MDX23C D1581",
     "MDX23C_D1581.ckpt", "MDX23C", "dual", "Balanced", 175),
    # These two were previously recorded as UNSUPPORTED with the reason
    # "checkpoint failed to load (state_dict mismatch)". That diagnosis was
    # WRONG. They load and separate perfectly. The real cause was GPU memory
    # exhaustion: `run-local.sh` ends in `exec uv run ...`, and `uv run`
    # forks, so pkill on the parent left the uvicorn child alive. Nine
    # orphaned workers had accumulated, two holding ~1 GB each on a 5.8 GB
    # card. audio-separator reports OOM during load as
    #   "model file is corrupt or incomplete"
    # which is what sent us down the wrong path. See scripts/restart-worker.sh.
    ("mbr_duality_v1", "Mel-Band RoFormer InstVoc Duality V1", "Duality V1",
     "melband_roformer_instvoc_duality_v1.ckpt", "MelBand-RoFormer", "dual",
     "Fuller sound", 1640),
    ("mbr_instvox_duality_v2", "Mel-Band RoFormer InstVox Duality V2",
     "InstVox Duality V2", "melband_roformer_instvox_duality_v2.ckpt",
     "MelBand-RoFormer", "dual", "Balanced", 1640),
]

# --- Vocal Tools models (probed 2026-10-10) ---------------------------------
#
# These populate the `Center / Male-Female` split that the Vocal Tools scene
# advertises but could not previously offer.
#
# ⚠️ The NAMES LIE about the OUTPUT, and the probe caught it:
#   - `model_chorus_bs_roformer_ep_267...` is named "chorus" but emits
#     **(male) + (female)** — it is a gender splitter, not a chorus extractor.
#   - `mel_band_roformer_crowd_...` emits (crowd) + (other).
#   - `vocals_mel_band_roformer` emits (vocals) + (other).
# Categories below are assigned from the OBSERVED stems, not the filenames.
VOCAL_TOOLS_MODELS = [
    # (id, name, short, registry, arch, target, trait, sizeMB, stems, categories)
    ("mbr_vocals_center", "Mel-Band RoFormer Vocals", "Vocals",
     "vocals_mel_band_roformer.ckpt", "MelBand-RoFormer", "vocals",
     "Balanced", 870, ["vocals", "other"], ["Center"]),
    ("bs_roformer_male_female", "BS-RoFormer Male / Female", "Male / Female",
     "bs_roformer_male_female_by_aufr33_sdr_7.2889.ckpt", "BS-RoFormer",
     "vocals", "Detailed split", 502, ["male", "female"], ["Male/Female"]),
    ("bs_roformer_gender_ep267", "BS-RoFormer Male / Female (EP267)",
     "Male / Female EP267",
     "model_chorus_bs_roformer_ep_267_sdr_24.1275.ckpt", "BS-RoFormer",
     "vocals", "Detailed split", 502, ["male", "female"], ["Male/Female"]),
    ("mbr_crowd", "Mel-Band RoFormer Crowd", "Crowd",
     "mel_band_roformer_crowd_aufr33_viperx_sdr_8.7144.ckpt",
     "MelBand-RoFormer", "vocals", "Noise reduction", 870,
     ["crowd", "other"], ["Crowd"]),
]

# --- Research-driven additions (probed 2026-10-10) --------------------------
#
# Sources supplied by a researcher pointing at the Politrees/UVR_resources HF
# mirror. Each was probed BEFORE being added; stems below are OBSERVED output,
# never inferred from the filename (dead end 3).
#
# NOTE on "vocals" as a stem name: UVR reuses `vocals` as the generic name for
# a 1-stem model's primary output. `melband_roformer_inst_metal_prev_by_mesk` has
# num_stems: 1, so its "(Vocals)" stem IS the metal. That is not a mistake.
HF_REPO = "Politrees/UVR_resources"
HF_BASE = "models/Roformer/MelBand"


def hf(*names: str) -> dict:
    """download.files payload for Politrees/UVR_resources."""
    return {
        "repo": HF_REPO,
        "repoType": "hf",
        "revision": "main",
        "files": [
            {"remote": f"{HF_BASE}/{n}", "dest": n, "size": 0} for n in names
        ],
    }


FRIEND_BATCH = [
    # (id, name, short, registry|None, arch, target, trait, sizeMB, stems, cats, download)
    ("mbr_bleed_suppressor", "Mel-Band RoFormer Bleed Suppressor", "Bleed Suppress",
     "mel_band_roformer_bleed_suppressor_v1.ckpt", "MelBand-RoFormer",
     "instrumental", "Low bleed", 870, ["bleed", "instrumental"], None, None),
    ("mbr_metal_mesk", "Metal Inst (MESK)", "Metal Inst",
     None, "MelBand-RoFormer", "instrumental", "Detailed split", 900,
     ["vocals", "other"], None,
     hf("melband_roformer_inst_metal_prev_by_mesk.ckpt",
        "config_melband_roformer_inst_metal_prev_by_mesk.yaml")),
    ("mbr_bve_gonza", "Lead / Backing Vocals (Gonza)", "Lead / Backing",
     None, "MelBand-RoFormer", "vocals", "Stable stems", 870,
     ["lead", "back"], None,
     hf("model_MelBand-Roformer_BVE_by-Gonza.ckpt",
        "config_MelBand-Roformer_BVE_by-Gonza.yaml")),
    ("mbr_duality_aname", "Mel-Band RoFormer Duality V1 (Aname)", "Duality Aname",
     None, "MelBand-RoFormer", "dual", "Balanced", 870,
     ["vocals", "other"], None,
     hf("model_MelBand-Roformer_Duality_v1_by-Aname.ckpt",
        "config_MelBand-Roformer_Duality_v1_by-Aname.yaml")),
    # Guitar initially looked like an unsupported architecture. It was not: the
    # config was byte-identical to the author's, and the checkpoint strict-loaded
    # once audio-separator's MelBand path was made to forward
    # mlp_expansion_factor (see backend._patch_melband_mlp_expansion). Verified
    # end-to-end: stems ['Other','Guitar'], 20.000 s, both audible.
    ("mbr_guitar_becruily", "Guitar (becruily)", "Guitar",
     None, "MelBand-RoFormer", "instrumental", "Detailed split", 41,
     ["guitar", "other"], None,
     hf("melband_roformer_guitar_becruily.ckpt",
        "config_melband_roformer_guitar_becruily.yaml")),
]

# --- Centre-image vocal extractors (R1, probed 2026-10-10) ------------------
#
# The registry labels these "BS-Roformer-Viperx-1297 / -1296"; the reference
# lists a Center group called Aufr33 and EP146. We do NOT claim they are those
# models — that mapping is unverified — so they are named by their registry
# identity and categorised from their OBSERVED output, which is
# (Vocals) + (Instrumental): a centre-image vocal extractor.
#
# Probed: ep_317 84.4s, ep_368 94.7s, both 2 stems, 609 MB each.
CENTRE_MODELS = [
    # (id, name, short, registry, arch, target, trait, sizeMB, stems, categories)
    ("bs_roformer_viperx_1297", "BS-RoFormer Viperx 1297", "Viperx 1297",
     "model_bs_roformer_ep_317_sdr_12.9755.ckpt", "BS-RoFormer", "dual",
     "Low bleed", 609, ["vocals", "instrumental"], ["Center"]),
    ("bs_roformer_viperx_1296", "BS-RoFormer Viperx 1296", "Viperx 1296",
     "model_bs_roformer_ep_368_sdr_12.9628.ckpt", "BS-RoFormer", "dual",
     "Stable stems", 609, ["vocals", "instrumental"], ["Center"]),
]

# Probed and FAILED to load — registered as unsupported so the picker hides
# them, with the actual failure as the reason.
# (both entries were promoted to VERIFIED above once the VRAM leak was fixed)
UNSUPPORTED: list = []

FAIL_REASON = (
    "Probed on this machine and the checkpoint failed to load "
    "(audio-separator reported a state_dict mismatch). Listed in the upstream "
    "registry but not runnable by this backend."
)

# --- Demucs variants (probed 2026-10-10) -------------------------------------
#
# The Stem Splitter scene had exactly ONE model (htdemucs_ft), which made it
# the thinnest scene in the app by a wide margin. audio-separator ships three
# more Demucs configurations; all three loaded here and produced valid stems.
#
# `htdemucs_6s` is the notable one: it splits six stems (drums, bass, vocals,
# guitar, piano, other) rather than four, so it is the only genuine `multi`
# target we have and it earns its place in the scene's `allowedTargets`.
# Sizes are the real on-disk weight files, not estimates.
STEM_MODELS = [
    # (id, name, short, registry, arch, target, trait, sizeMB, stems)
    ("htdemucs", "HTDemucs", "HTDemucs", "htdemucs.yaml", "HTDemucs",
     "4-stem", "Balanced", 80, ["drums", "bass", "vocals", "other"]),
    ("hdemucs_mmi", "Hybrid Demucs (MMI)", "Hybrid Demucs", "hdemucs_mmi.yaml",
     "HybridDemucs", "4-stem", "Detailed split", 159,
     ["drums", "bass", "vocals", "other"]),
    ("htdemucs_6s", "HTDemucs 6-Source", "HTDemucs 6S", "htdemucs_6s.yaml",
     "HTDemucs", "multi", "Dual stems", 52,
     ["drums", "bass", "vocals", "guitar", "piano", "other"]),
]

# Closed against the live reference site 2026-10-10. Its Instrument Extractor
# offers dedicated single-instrument models (Kick, Snare, Hi-Hat, Toms, Congas,
# Timpani, Tambourine, Triangle, Gilliaan Drums, SCNet Jazz Piano/Drums). Of
# those, only these three are obtainable from any open registry — the BS Mega 53
# family, SCNet and Gilliaan Drums have zero open entries and are permanently
# out of reach. `stems` and `instruments` below are what was OBSERVED on a real
# run, never what the filename suggests.
PARITY_BATCH = [
    # (id, name, short, registry, arch, target, trait, sizeMB,
    #  stems, categories, download, instruments)
    ("drumsep_mdx23c", "DrumSep (MDX23C)", "DrumSep", "MDX23C-DrumSep-aufr33-jarredou.ckpt",
     "MDX-C", "multi", "Drum family detail", 448,
     ["kick", "snare", "toms", "hh", "ride", "crash"], None, None,
     ["kick", "snare", "toms", "hihat", "ride", "crash"]),
    ("htdemucs_ft", "HTDemucs Fine-Tuned", "HTDemucs FT", "htdemucs_ft.yaml",
     "HTDemucs", "4-stem", "Fine-tuned split", 320,
     ["drums", "bass", "vocals", "other"], None, None,
     ["drums", "bass"]),
    ("mdx_dereverb", "De-Reverb (MDX23C)", "De-Reverb", "MDX23C-De-Reverb-aufr33-jarredou.ckpt",
     "MDX-C", "dual", "Reverb removal", 448,
     ["dry", "No dry"], ["Dereverb"], None, None),
]

# Explicit repair capabilities. Deliberately NOT derived from `target`: a model
# being `dual` or `instrumental` says nothing about whether it performs a
# repair, so eligibility is its own declared field.
#
# Every value here was MEASURED by scripts/test-repair-models.py, which runs the
# model on a degraded fixture and correlates each output against the known-clean
# signal. primaryStem is the stem that wins by a decisive margin; it is never a
# guess and never outputs[0].
#
#   model                    fixture   clean ref     winner       r      residue r
#   mdx_dereverb             reverb    probe_clip    Dry        +0.826    0.208
#   mbr_bleed_suppressor     bleed     clean_inst    Instrumental +0.992   0.105
#   mbr_crowd                bleed     clean_inst    Other      +0.972    0.070
#
# All three preserve 2 channels and the source sample rate.
REPAIR_CAPABILITIES = {
    "mdx_dereverb": {
        "categories": ["dereverb"],
        "primaryStem": "Dry",
        "inputScope": "full-mix",
        "preservesChannels": True,
    },
    "mbr_bleed_suppressor": {
        "categories": ["denoise"],
        "primaryStem": "Instrumental",
        "inputScope": "full-mix",
        "preservesChannels": True,
    },
    "mbr_crowd": {
        "categories": ["live-cleanup"],
        "primaryStem": "Other",
        "inputScope": "full-mix",
        "preservesChannels": True,
    },
}


def _unpack(spec):
    """Normalise a spec to a dict.

    Specs are positional tuples and have grown optional trailing fields
    (`stems`, `categories`), so every unpacker goes through here rather than
    branching on `len()` in three places.
    """
    keys = [
        "id", "name", "short", "registry", "arch", "target", "trait",
        "size", "stems", "categories", "download", "instruments",
    ]
    data = dict(zip(keys, spec))
    data.setdefault("stems", None)
    data.setdefault("categories", None)
    data.setdefault("download", None)
    data.setdefault("instruments", None)
    return data


def worker_entry(spec) -> dict:
    d = _unpack(spec)
    # Positional tuples drift silently: a spec that is one field short lands its
    # last value in the wrong key and writes a nonsense catalog entry (this has
    # already happened — an `instruments` list was written into `download` and
    # took the whole worker down on import). Fail loudly instead.
    for key in ("download", "instruments"):
        if d[key] is not None and not isinstance(d[key], (list, dict)):
            raise SystemExit(
                f"{d['id']}: field '{key}' is a {type(d[key]).__name__}, not a list/dict. "
                "The spec tuple is misaligned with _unpack()'s key order."
            )
    if d["download"] is not None and d["registry"] is None and isinstance(d["download"], str):
        raise SystemExit(f"{d['id']}: 'download' received a string (probably the registry name).")
    entry = {
        "name": d["name"],
        "arch": d["arch"],
        "target": d["target"],
        "tags": [d["trait"].lower()],
        "sizeMB": d["size"],
        "source": (
            "Hugging Face Politrees/UVR_resources"
            if d["download"] else "audio-separator model registry"
        ),
        "sdr": None,
        "model_type": "vocal_models",
        "license": "UNSPECIFIED",
    }
    # A model has exactly ONE fetch path. Emitting both would let the two
    # disagree about which file is authoritative.
    if d["download"]:
        entry["download"] = d["download"]
    else:
        entry["registry"] = d["registry"]
    if d["stems"]:
        entry["stems"] = d["stems"]
    if d["categories"]:
        entry["categories"] = d["categories"]
    if d["instruments"]:
        entry["instrumentTargets"] = d["instruments"]
    return entry


def unsupported_entry(spec) -> dict:
    mid, name, _short, registry, arch, target = spec
    return {
        "registry": registry,
        "unsupported": FAIL_REASON,
        "name": name,
        "arch": arch,
        "target": target,
        "tags": [],
        "sizeMB": 0,
        "source": "audio-separator model registry",
        "sdr": None,
        "model_type": "vocal_models",
        "license": "UNSPECIFIED",
    }


def ui_entry(spec) -> str:
    d = _unpack(spec)
    stems_line = f'    stems: {json.dumps(d["stems"])},\n' if d["stems"] else ""
    cats_line = (
        f'    categories: {json.dumps(d["categories"])},\n' if d["categories"] else ""
    )
    instr_line = (
        f'    instrumentTargets: {json.dumps(d["instruments"])},\n'
        if d["instruments"] else ""
    )
    # The UI never needs the fetch path — `getModelStatus` asks the worker —
    # but it must know the source so the card can say where a model came from.
    source = (
        "Hugging Face Politrees/UVR_resources"
        if d["download"] else "audio-separator model registry"
    )
    return (
        "  {\n"
        f'    id: "{d["id"]}",\n'
        f'    name: "{d["name"]}",\n'
        f'    shortName: "{d["short"]}",\n'
        f'    arch: "{d["arch"]}",\n'
        f'    target: "{d["target"]}",\n'
        f"    tags: [\"{d['trait'].lower()}\"],\n"
        f"    sizeMB: {d['size']},\n"
        f"{stems_line}{cats_line}{instr_line}"
        f'    source: "{source}",\n'
        "  },\n"
    )


def ui_unsupported_entry(spec) -> str:
    mid, name, short, _registry, arch, target = spec
    reason = FAIL_REASON.replace('"', "'")
    return (
        "  {\n"
        f'    id: "{mid}",\n'
        f'    unsupported:\n      "{reason}",\n'
        f'    name: "{name}",\n'
        f'    shortName: "{short}",\n'
        f'    arch: "{arch}",\n'
        f'    target: "{target}",\n'
        "    tags: [],\n"
        "    sizeMB: 0,\n"
        '    source: "audio-separator model registry",\n'
        "  },\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    VERIFIED_ALL = (
        VERIFIED + STEM_MODELS + VOCAL_TOOLS_MODELS + CENTRE_MODELS + FRIEND_BATCH
        + PARITY_BATCH
    )

    catalog = json.loads(WORKER.read_text(encoding="utf-8"))
    added, skipped, updated = [], [], []

    for spec in VERIFIED_ALL:
        mid = spec[0]
        if mid in catalog:
            # Back-fill metadata that arrived after the model was first added.
            # Repair capabilities are measured later than the model is
            # discovered. Additive only — never touch stems/target, which came
            # from the probe itself.
            cap = REPAIR_CAPABILITIES.get(mid)
            if cap and catalog[mid].get("repair") != cap:
                catalog[mid]["repair"] = cap
                updated.append(mid)
            skipped.append(mid)
            continue
        catalog[mid] = worker_entry(spec)
        added.append(mid)
    for spec in UNSUPPORTED:
        mid = spec[0]
        if mid in catalog:
            skipped.append(mid)
            continue
        catalog[mid] = unsupported_entry(spec)
        added.append(mid)

    ui = UI.read_text(encoding="utf-8")

    # --- locate TRAIT_BY_ID and BASE_MODELS by their DECLARATIONS -----------
    #
    # Anchoring on each block's last entry is fragile: every run appends to it,
    # so the anchor text changes and the NEXT run silently finds nothing (and
    # does a partial write). Anchoring on the declaration and walking to the
    # matching close brace is stable no matter what has been added before.
    DECL_TRAIT = "const TRAIT_BY_ID: Record<string, string> = {"
    DECL_MODELS = "const BASE_MODELS: Model[] = ["
    for decl in (DECL_TRAIT, DECL_MODELS):
        if decl not in ui:
            print(f"error: declaration not found in models.ts: {decl!r}",
                  file=sys.stderr)
            print("       models.ts has been restructured — update this script.",
                  file=sys.stderr)
            return 2

    def block_end(source: str, decl: str) -> int:
        """Index of the `}` / `]` that closes the block opened at `decl`."""
        i = source.index(decl) + len(decl)
        depth = 1
        while depth:
            ch = source[i]
            if ch in "{[":
                depth += 1
            elif ch in "}]":
                depth -= 1
                if depth == 0:
                    return i
            i += 1
        raise AssertionError("unbalanced models.ts")

    # The trait table is the other half of "add to both": without it a new
    # model falls back to tags[0] and the derived Traits filter shows a raw
    # lowercase tag instead of the promise we just wrote.
    #
    # Accumulate ALL new lines and splice once.
    new_trait_lines = "".join(
        f'  {spec[0]}: "{spec[6]}",\n'
        for spec in VERIFIED_ALL
        if f"  {spec[0]}:" not in ui
    )
    if new_trait_lines:
        end = block_end(ui, DECL_TRAIT)
        ui = ui[:end] + new_trait_lines + ui[end:]

    # Only emit entries whose id is not already present. Keying on a "marker
    # comment already present" guard is wrong: once the first batch lands, that
    # guard blocks every LATER batch from adding anything. Idempotency has to
    # be per-model, not per-block.
    def ui_missing(spec) -> bool:
        return f'id: "{spec[0]}",' not in ui

    new_blocks = "".join(ui_entry(s) for s in VERIFIED_ALL if ui_missing(s))
    new_blocks += "".join(
        ui_unsupported_entry(s) for s in UNSUPPORTED if ui_missing(s)
    )
    if new_blocks.strip():
        end = block_end(ui, DECL_MODELS)
        ui = (
            ui[:end]
            + "\n  // Registry-backed models verified by probe"
              " (scripts/probe-registry-model.py)\n"
            + new_blocks
            + ui[end:]
        )

    # Back-fill `repair` into models.ts for models that were added before their
    # capability was measured. Inserted immediately before each entry's closing
    # brace, so it does not depend on where the entry sits in the array.
    if not args.dry_run:
        for mid, cap in REPAIR_CAPABILITIES.items():
            marker = f'id: "{mid}",'
            if marker not in ui:
                continue
            if "    repair: {" in ui[ui.index(marker):ui.index(marker) + 900]:
                continue
            start = ui.index(marker)
            # Walk from the entry's opening brace to its matching close, then
            # back up to the START OF THAT LINE. Inserting at the `}` itself
            # would split `  },` into stray indentation plus a column-0 brace.
            depth, i = 1, start + 3
            while depth:
                if ui[i] == "{":
                    depth += 1
                elif ui[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            line_start = ui.rfind("\n", 0, i) + 1
            body = (
                "    repair: {\n"
                f'      categories: {json.dumps(cap["categories"])},\n'
                f'      primaryStem: "{cap["primaryStem"]}",\n'
                f'      inputScope: "{cap["inputScope"]}",\n'
                f'      preservesChannels: {str(cap["preservesChannels"]).lower()},\n'
                "    },\n"
            )
            ui = ui[:line_start] + body + ui[line_start:]
            updated.append(f"{mid}(ui)")

    # Post-conditions: the UI must contain every id AND every trait entry.
    # A silent partial write is exactly how 12 models ended up with lowercase
    # traits, so these are asserted rather than assumed.
    missing_ui = [s[0] for s in VERIFIED_ALL + UNSUPPORTED if f'id: "{s[0]}",' not in ui]
    missing_trait = [s[0] for s in VERIFIED_ALL if f'  {s[0]}: "{s[6]}",' not in ui]
    if missing_ui:
        print(f"error: these ids did not land in models.ts: {missing_ui}",
              file=sys.stderr)
        return 2
    if missing_trait:
        print(f"error: these TRAIT_BY_ID entries did not land: {missing_trait}",
              file=sys.stderr)
        return 2

    print(f"worker catalog: {len(catalog)} entries (+{len(added)} new)")
    if skipped:
        print(f"  already present, skipped: {', '.join(skipped)}")
    print(f"  added: {', '.join(added) if added else '(none)'}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0

    WORKER.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    UI.write_text(ui, encoding="utf-8")
    print(f"wrote {WORKER.relative_to(ROOT)} and {UI.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())