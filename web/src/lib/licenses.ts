/**
 * Model license registry — VERIFIED against the upstream sources.
 *
 * This file exists because "available on Hugging Face" does NOT mean
 * "free to use". Several popular separation checkpoints carry
 * non-commercial or undeclared licenses. Each entry records what was
 * actually found on the model page so the UI can be honest about it.
 *
 * Verified 2026-09-16:
 *   - facebookresearch/demucs (HTDemucs) .......... MIT
 *   - sigsep/open-unmix-pytorch (umxhq, umx) ...... MIT
 *   - deezer/spleeter ............................. MIT
 *   - anvuew/BS-RoFormer .......................... GPL-3.0
 *   - becruily/mel-band-roformer-deux ............. CC-BY-NC-4.0 (NonCommercial)
 *   - pcunwa/BS-Roformer-HyperACE ................. NO LICENSE DECLARED
 *   - GaboxR67/MelBandRoformers ................... NO LICENSE DECLARED
 */

export type LicenseKind =
  | "MIT"
  | "Apache-2.0"
  | "GPL-3.0"
  | "CC-BY-NC-4.0"
  | "UNSPECIFIED";

export interface LicenseInfo {
  /** SPDX-style identifier (or UNSPECIFIED when none is declared). */
  kind: LicenseKind;
  /** Human-readable label for badges. */
  label: string;
  /** Can this be used commercially without further permission? */
  commercialOk: boolean;
  /** Where the license was verified. */
  source: string;
}

export const LICENSES: Record<LicenseKind, LicenseInfo> = {
  MIT: {
    kind: "MIT",
    label: "MIT",
    commercialOk: true,
    source: "Permissive — free for any use, including commercial.",
  },
  "Apache-2.0": {
    kind: "Apache-2.0",
    label: "Apache-2.0",
    commercialOk: true,
    source: "Permissive — free for any use, including commercial.",
  },
  "GPL-3.0": {
    kind: "GPL-3.0",
    label: "GPL-3.0",
    commercialOk: true,
    source:
      "Copyleft — free to use; derivative works must also be GPL-3.0 licensed.",
  },
  "CC-BY-NC-4.0": {
    kind: "CC-BY-NC-4.0",
    label: "CC-BY-NC-4.0",
    commercialOk: false,
    source: "NonCommercial — personal/research use only. NOT for commercial use.",
  },
  UNSPECIFIED: {
    kind: "UNSPECIFIED",
    label: "No license",
    commercialOk: false,
    source:
      "No license declared upstream. Default copyright applies — treat as all rights reserved until the author clarifies.",
  },
};

/**
 * Per-checkpoint license overrides for the catalog.
 * Anything not listed falls back to the architecture default.
 */
export const MODEL_LICENSE: Record<string, LicenseKind> = {
  // Locally installed MSST checkpoints
  becruily_deux: "CC-BY-NC-4.0",
  mbr_instfv9_gabox: "UNSPECIFIED",
  mbr_instfv9_2_gabox: "UNSPECIFIED",
  bs_roformer_inst_hyperacev2_ckpt: "UNSPECIFIED",

  // Catalog entries
  bs_roformer_voc_hyperacev2: "UNSPECIFIED",
  bs_roformer_inst_hyperacev2: "UNSPECIFIED",
  bs_roformer_voc_resurrection: "UNSPECIFIED",
  bs_roformer_inst_resurrection: "UNSPECIFIED",
  bs_polarformer_vocals: "UNSPECIFIED",
  mel_band_roformer_deux: "CC-BY-NC-4.0",
  mel_band_roformer_flowers_v10: "UNSPECIFIED",
  mel_band_roformer_fv9: "UNSPECIFIED",
  mel_band_roformer_fv8b: "UNSPECIFIED",
  mel_band_roformer_inst_v1e: "UNSPECIFIED",

  // Permissive foundation models
  mdx23c_instvoc_hq: "MIT",
  htdemucs_4stem: "MIT",
};

export function licenseFor(modelId: string, arch?: string): LicenseInfo {
  const kind =
    MODEL_LICENSE[modelId] ??
    (arch === "HTDemucs" || arch === "MDX23C" ? "MIT" : "UNSPECIFIED");
  return LICENSES[kind];
}
