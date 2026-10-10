#!/usr/bin/env python3
"""
Prove (or disprove) the mlp_expansion_factor hypothesis for a Roformer checkpoint.

Context: audio-separator's `uvr_lib_v5/roformer/mel_band_roformer.py` builds its
mask estimator like this:

    mask_estimator = MaskEstimator(dim=dim,
                                   dim_inputs=freqs_per_bands_with_complex,
                                   depth=mask_estimator_depth)          # <- no factor

while `MaskEstimator.__init__` defaults `mlp_expansion_factor=4`. The sibling
`bs_roformer.py` DOES forward the factor. So for a checkpoint trained with
`mlp_expansion_factor: 1`, MelBand builds a hidden width of `dim * 4` while the
weights expect `dim * 1` — exactly the 256-vs-1024 mismatch seen on guitar.

This script answers three questions without touching a catalogue:
  1. does the installed loader FORWARD the factor to the mask estimator?
  2. does the checkpoint then strict-load?
  3. if not, which keys still differ?

Usage:
  cd api && .venv/bin/python ../scripts/check-roformer-compat.py \
      --config /tmp/uvr-guitar-debug/config_guitar_becruily.yaml \
      --checkpoint /path/to/guitar.ckpt
"""

from __future__ import annotations

import argparse
import gc
import sys
from collections.abc import Mapping
from pathlib import Path

import torch
import yaml

FACTORS = (1, 4)


def load_state(path: str) -> dict:
    """Load a checkpoint and unwrap the usual state_dict containers."""
    obj = torch.load(path, map_location="cpu", weights_only=True)
    if isinstance(obj, Mapping):
        for key in ("state_dict", "model_state_dict", "model"):
            value = obj.get(key)
            if isinstance(value, Mapping):
                obj = value
                break
    if not isinstance(obj, Mapping):
        raise TypeError("Checkpoint is not a state-dictionary mapping")
    if not obj or not all(isinstance(v, torch.Tensor) for v in obj.values()):
        raise TypeError("Checkpoint contains non-tensor state entries")
    if all(k.startswith("module.") for k in obj):
        obj = {k.removeprefix("module."): v for v, k in
               ((v, k) for k, v in obj.items())}
    return dict(obj)


def build_loader_model(model_cfg: dict, factor: int):
    """Construct through audio-separator's own config -> factory path.

    `factor` overrides the config so both candidates can be compared without
    editing the YAML.
    """
    from audio_separator.separator.roformer.roformer_loader import RoformerLoader
    from audio_separator.separator.roformer.mel_band_roformer_config import (
        MelBandRoformerConfig,
    )

    raw = dict(model_cfg, mlp_expansion_factor=factor)
    cfg = MelBandRoformerConfig.from_dict({"model": raw})
    return RoformerLoader().load_model(cfg)


def to_freqs_hidden(model: torch.nn.Module) -> set[int]:
    """`to_freqs[i][0]` is Linear(dim_in -> dim_hidden); its weight is
    [dim_hidden, dim_in]. Reading dim_hidden off the built module is the
    direct, checkpoint-independent measurement."""
    out: set[int] = set()
    for name, tensor in model.state_dict().items():
        if "mask_estimators" in name and ".to_freqs." in name and tensor.dim() == 2:
            out.add(int(tensor.shape[0]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--checkpoint", required=True)
    args = ap.parse_args()

    # FullLoader, not safe_load: these configs use !!python/tuple.
    with open(args.config) as fh:
        config = yaml.load(fh, Loader=yaml.FullLoader)
    model_cfg = dict(config.get("model") or {})
    print(f"config: {args.config}")
    print(f"config model block: dim={model_cfg.get('dim')} "
          f"dim_freqs_in={model_cfg.get('dim_freqs_in')} "
          f"stft_n_fft={model_cfg.get('stft_n_fft')} "
          f"mask_estimator_depth={model_cfg.get('mask_estimator_depth')} "
          f"mlp_expansion_factor={model_cfg.get('mlp_expansion_factor', 'ABSENT')}")

    state = load_state(args.checkpoint)
    ckpt_widths = sorted({int(v.shape[0]) for k, v in state.items()
                          if "mask_estimators" in k and ".to_freqs." in k
                          and v.dim() == 2})
    print(f"\ncheckpoint tensors      : {len(state)}")
    print(f"checkpoint mask-MLP out : {ckpt_widths}")

    strict_ok: set[int] = set()
    for factor in FACTORS:
        model = None
        built = None
        try:
            model = build_loader_model(model_cfg, factor).cpu()
            built = model.state_dict()
            widths = sorted(to_freqs_hidden(model))
            missing = sorted(set(state) - set(built))
            unexpected = sorted(set(built) - set(state))
            mismatched = [
                (k, tuple(built[k].shape), tuple(state[k].shape))
                for k in sorted(set(state) & set(built))
                if built[k].shape != state[k].shape
            ]
            print(f"\nfactor={factor}: built mask-MLP out={widths}  "
                  f"missing={len(missing)} unexpected={len(unexpected)} "
                  f"shape_mismatches={len(mismatched)}")
            for k, b, c in mismatched[:6]:
                print(f"    {k}: built={b} checkpoint={c}")
            for k in missing[:4]:
                print("    missing:", k)
            for k in unexpected[:4]:
                print("    unexpected:", k)
            if not missing and not unexpected and not mismatched:
                model.load_state_dict(state, strict=True)
                strict_ok.add(factor)
                print(f"    STRICT LOAD PASSED at factor={factor}")
        except Exception as exc:  # noqa: BLE001
            print(f"\nfactor={factor}: {type(exc).__name__}: {exc}")
        finally:
            del built, model
            gc.collect()

    print("\n" + "=" * 68)
    try:
        forwarded = sorted(to_freqs_hidden(build_loader_model(model_cfg, 1).cpu()))
    except Exception as exc:  # noqa: BLE001
        forwarded = [f"error: {exc}"]
    print(f"with config factor=1 the installed loader builds to_freqs widths {forwarded}")
    if ckpt_widths and sorted(forwarded) != ckpt_widths:
        print("=> LOADER DOES NOT FORWARD mlp_expansion_factor (defaults to 4). "
              "This is the bug.")
    if 1 in strict_ok:
        print("=> checkpoint strict-loads at factor 1; the config is correct and "
              "only the forwarding is missing.")
        return 0
    if strict_ok:
        print(f"=> strict load only at factor {sorted(strict_ok)} — config disagrees")
        return 3
    print("=> no factor produces a strict load; deeper mismatch than the factor")
    return 2


if __name__ == "__main__":
    sys.exit(main())