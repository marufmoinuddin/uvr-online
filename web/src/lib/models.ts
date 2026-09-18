import type { Model, SceneKey, SceneMeta } from "./types";

/**
 * Model catalog — seeded from verified HF sources (spec §5) plus the
 * models actually installed in the local MSST-WebUI stack. The API worker
 * merges this with the live `models.json` / `models_info.json` at runtime.
 */
const BASE_MODELS: Model[] = [
  // BS-RoFormer family
  {
    id: "bs_roformer_voc_hyperacev2",
    name: "BS-RoFormer Vocals HyperACE v2",
    arch: "BS-RoFormer",
    target: "vocals",
    tags: ["clean", "low-bleed"],
    sizeMB: 180,
    source: "pcunwa/BS-Roformer-HyperACE",
    sdr: 12.4,
  },
  {
    id: "bs_roformer_inst_hyperacev2",
    name: "BS-RoFormer Instrumental HyperACE v2",
    arch: "BS-RoFormer",
    target: "instrumental",
    tags: ["clean", "low-bleed"],
    sizeMB: 185,
    source: "pcunwa/BS-Roformer-HyperACE",
    sdr: 12.1,
  },
  {
    id: "bs_roformer_voc_resurrection",
    name: "BS-RoFormer Vocals Resurrection",
    arch: "BS-RoFormer",
    target: "vocals",
    tags: ["fullness"],
    sizeMB: 204,
    source: "pcunwa/BS-Roformer-Resurrection",
    sdr: 12.8,
  },
  {
    id: "bs_roformer_inst_resurrection",
    name: "BS-RoFormer Instrumental Resurrection",
    arch: "BS-RoFormer",
    target: "instrumental",
    tags: ["fullness", "low-bleed"],
    sizeMB: 204,
    source: "pcunwa/BS-Roformer-Resurrection",
    sdr: 12.5,
  },
  {
    id: "bs_polarformer_vocals",
    name: "BS-PolarFormer Vocals",
    arch: "BS-PolarFormer",
    target: "vocals",
    tags: ["clean", "karaoke"],
    sizeMB: 175,
    source: "pcunwa/BS-EXP-SiameseRoformer",
    sdr: 12.9,
  },

  // MelBand-RoFormer family
  {
    id: "mel_band_roformer_deux",
    name: "Mel-Band RoFormer Deux",
    arch: "MelBand-RoFormer",
    target: "dual",
    tags: ["fullness", "balanced"],
    sizeMB: 192,
    source: "becruily/mel-band-roformer-deux",
    sdr: 11.9,
  },
  {
    id: "mel_band_roformer_flowers_v10",
    name: "Mel-Band RoFormer Flowers v10",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["fullness", "low-bleed"],
    sizeMB: 210,
    source: "GaboxR67/MelBandRoformers",
    sdr: 12.2,
  },
  {
    id: "mel_band_roformer_fv9",
    unsupported:
      "No download source is configured for this model yet, so it cannot be fetched.",
    name: "Mel-Band RoFormer Fv9",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["fullness"],
    sizeMB: 205,
    source: "GaboxR67/MelBandRoformers",
    sdr: 12.0,
  },
  {
    id: "mel_band_roformer_fv8b",
    name: "Mel-Band RoFormer Fv8b",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["fullness", "detail"],
    sizeMB: 200,
    source: "GaboxR67/MelBandRoformers",
    sdr: 11.8,
  },
  {
    id: "mel_band_roformer_inst_v1e",
    name: "Mel-Band RoFormer Inst v1e",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["fullness", "classic"],
    sizeMB: 198,
    source: "pcunwa/Mel-Band-Roformer-Inst",
    sdr: 11.7,
  },

  // MDX / Demucs / other
  {
    id: "mdx23c_instvoc_hq",
    name: "MDX23C InstVoc HQ",
    arch: "MDX23C",
    target: "dual",
    tags: ["baseline", "hq"],
    sizeMB: 160,
    source: "audio-separator model registry",
    sdr: 10.9,
  },
  {
    id: "htdemucs_4stem",
    name: "HTDemucs 4-Stem",
    arch: "HTDemucs",
    target: "4-stem",
    tags: ["drums", "bass", "vocals", "other"],
    sizeMB: 320,
    source: "facebookresearch/demucs",
    sdr: 11.4,
    stems: ["drums", "bass", "vocals", "other"],
  },

  // Locally installed MSST models (verified in this workspace)
  {
    id: "mbr_instfv9_gabox",
    name: "Mel-Band RoFormer Inst Fv9 (Gabox)",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["fullness", "installed"],
    sizeMB: 913,
    source: "noblebarkrr/mvsepless_resources",
    sdr: 12.0,
    installed: true,
  },
  {
    id: "mbr_instfv9_2_gabox",
    name: "Mel-Band RoFormer Inst Fv9-2 (Gabox)",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["fullness", "installed"],
    sizeMB: 913,
    source: "noblebarkrr/mvsepless_resources",
    sdr: 12.0,
    installed: true,
  },
  {
    id: "becruily_deux",
    name: "Mel-Band RoFormer Deux (becruily)",
    arch: "MelBand-RoFormer",
    target: "dual",
    tags: ["balanced", "installed"],
    sizeMB: 435,
    source: "becruily/mel-band-roformer-deux",
    sdr: 11.9,
    installed: true,
  },
  {
    id: "bs_roformer_inst_hyperacev2_ckpt",
    name: "BS-RoFormer Inst HyperACE v2 (ckpt)",
    arch: "BS-RoFormer",
    target: "instrumental",
    tags: ["clean", "low-bleed", "installed"],
    sizeMB: 289,
    source: "pcunwa/BS-Roformer-HyperACE",
    sdr: 12.1,
    installed: true,
  },
];

/** Workbench trait shown on each model card (mirrors the reference site). */
const TRAIT_BY_ID: Record<string, string> = {
  bs_roformer_voc_hyperacev2: "Low bleed",
  bs_roformer_inst_hyperacev2: "Low bleed",
  bs_roformer_voc_resurrection: "Fuller sound",
  bs_roformer_inst_resurrection: "Detailed split",
  bs_polarformer_vocals: "Detailed split",
  mel_band_roformer_deux: "Stable stems",
  mel_band_roformer_flowers_v10: "Natural tone",
  mel_band_roformer_fv9: "Stable stems",
  mel_band_roformer_fv8b: "Stable stems",
  mel_band_roformer_inst_v1e: "Dual stems",
  mdx23c_instvoc_hq: "High quality",
  htdemucs_4stem: "Dual stems",
  mbr_instfv9_gabox: "Stable stems",
  mbr_instfv9_2_gabox: "Stable stems",
  becruily_deux: "Stable stems",
  bs_roformer_inst_hyperacev2_ckpt: "Low bleed",
};

export function modelTrait(m: Model): string {
  return TRAIT_BY_ID[m.id] ?? m.trait ?? m.tags[0] ?? "Balanced";
}

/** Ensemble presets — fuse multiple models (runs 2–6 model passes). */
const ENSEMBLE_PRESETS: Model[] = [
  {
    id: "ens_inst_avg_fft",
    name: "Inst · avg_fft",
    arch: "Ensemble",
    target: "instrumental",
    tags: ["Balanced", "Ensemble"],
    sizeMB: 0,
    source: "ensemble",
    usage: "3+ passes",
    ensemble: true,
    trait: "Balanced",
  },
  {
    id: "ens_inst_avg_wave",
    name: "Inst · avg_wave",
    arch: "Ensemble",
    target: "instrumental",
    tags: ["Balanced", "Ensemble"],
    sizeMB: 0,
    source: "ensemble",
    usage: "3+ passes",
    ensemble: true,
    trait: "Balanced",
  },
  {
    id: "ens_inst_max_fft",
    name: "Inst · max_fft",
    arch: "Ensemble",
    target: "instrumental",
    tags: ["Fuller sound", "Ensemble"],
    sizeMB: 0,
    source: "ensemble",
    usage: "3+ passes",
    ensemble: true,
    trait: "Fuller sound",
  },
  {
    id: "ens_inst_max_wave",
    name: "Inst · max_wave",
    arch: "Ensemble",
    target: "instrumental",
    tags: ["Fuller sound", "Ensemble"],
    sizeMB: 0,
    source: "ensemble",
    usage: "3+ passes",
    ensemble: true,
    trait: "Fuller sound",
  },
  {
    id: "ens_inst_median_fft",
    name: "Inst · median_fft",
    arch: "Ensemble",
    target: "instrumental",
    tags: ["Stable stems", "Ensemble"],
    sizeMB: 0,
    source: "ensemble",
    usage: "3+ passes",
    ensemble: true,
    trait: "Stable stems",
    recommended: true,
  },
  {
    id: "ens_inst_median_wave",
    name: "Inst · median_wave",
    arch: "Ensemble",
    target: "instrumental",
    tags: ["Stable stems", "Ensemble"],
    sizeMB: 0,
    source: "ensemble",
    usage: "3+ passes",
    ensemble: true,
    trait: "Stable stems",
  },
  {
    id: "ens_inst_min_fft",
    name: "Inst · min_fft",
    arch: "Ensemble",
    target: "instrumental",
    tags: ["Low bleed", "Ensemble"],
    sizeMB: 0,
    source: "ensemble",
    usage: "3+ passes",
    ensemble: true,
    trait: "Low bleed",
  },
  {
    id: "ens_inst_min_wave",
    name: "Inst · min_wave",
    arch: "Ensemble",
    target: "instrumental",
    tags: ["Low bleed", "Ensemble"],
    sizeMB: 0,
    source: "ensemble",
    usage: "3+ passes",
    ensemble: true,
    trait: "Low bleed",
  },
];

export const MODEL_CATALOG: Model[] = [...BASE_MODELS, ...ENSEMBLE_PRESETS];

export const SCENES: SceneMeta[] = [
  {
    key: "vocal-remover",
    label: "Vocal Remover",
    short: "Remove Vocals",
    description: "Remove vocals from any song and keep the instrumental.",
    icon: "mic-off",
    defaultModelId: "becruily_deux",
    allowedTargets: ["instrumental", "dual"],
  },
  {
    key: "extract-vocals",
    label: "Extract Vocals",
    short: "Extract Vocals",
    description: "Isolate the vocal track from any song.",
    icon: "mic",
    defaultModelId: "becruily_deux",
    allowedTargets: ["vocals", "dual"],
  },
  {
    key: "karaoke",
    label: "Karaoke Maker",
    short: "Karaoke",
    description: "Turn any song into a karaoke track.",
    icon: "music",
    defaultModelId: "becruily_deux",
    allowedTargets: ["instrumental", "dual"],
  },
  {
    key: "stem-splitter",
    label: "Stem Splitter",
    short: "4-Stem",
    description: "Split into drums, bass, vocals and other.",
    icon: "layers",
    defaultModelId: "htdemucs_4stem",
    allowedTargets: ["4-stem", "multi"],
    multiStem: true,
  },
  {
    key: "denoise",
    label: "Remove Background Noise",
    short: "Noise Removal",
    description: "Clean up hiss, hum and background noise.",
    icon: "waves",
    defaultModelId: "mdx23c_instvoc_hq",
    allowedTargets: ["dual"],
  },
  {
    key: "acapella",
    label: "Acapella Extractor",
    short: "Acapella",
    description: "Extract pure acapella vocals.",
    icon: "mic-vocal",
    defaultModelId: "becruily_deux",
    allowedTargets: ["vocals", "dual"],
  },
  {
    key: "vocal-tools",
    label: "Vocal Tools",
    short: "Vocal Tools",
    description: "Dereverb, gender split and vocal effects.",
    icon: "sliders-horizontal",
    defaultModelId: "becruily_deux",
    allowedTargets: ["vocals", "dual"],
  },
  {
    key: "production",
    label: "Production Tools",
    short: "Production",
    description: "Pitch shift, time stretch and alignment.",
    icon: "audio-lines",
    defaultModelId: "mel_band_roformer_deux",
    allowedTargets: ["dual", "4-stem"],
  },
  {
    key: "model-picker",
    label: "Full Model Picker",
    short: "Model Picker",
    description: "Full model picker — all 80+ architectures.",
    icon: "grid-2x2",
    defaultModelId: "mel_band_roformer_deux",
    allowedTargets: ["vocals", "instrumental", "dual", "4-stem", "multi"],
  },
];

export function getScene(key: string): SceneMeta {
  return SCENES.find((s) => s.key === key) ?? SCENES[0];
}

export function getModel(id: string): Model | undefined {
  return MODEL_CATALOG.find((m) => m.id === id);
}

export function modelsByArch(arch: string): Model[] {
  return MODEL_CATALOG.filter((m) => m.arch === arch);
}

export const ARCHITECTURES = Array.from(
  new Set(MODEL_CATALOG.map((m) => m.arch)),
).sort();

export function modelsForScene(
  scene: SceneKey,
  models: Model[] = MODEL_CATALOG,
): Model[] {
  const meta = getScene(scene);
  return models.filter(
    (m) =>
      meta.allowedTargets.includes(m.target) &&
      // Models the backend cannot load (e.g. a custom architecture its
      // engine does not implement) are never offered for selection.
      !m.unsupported,
  );
}