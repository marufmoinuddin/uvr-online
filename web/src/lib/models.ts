import type { Model, SceneKey, SceneMeta, UsageTier } from "./types";

/**
 * Model catalog — seeded from verified HF sources (spec §5) plus the
 * checkpoints shipped in `api/models.json`. The worker's live catalog is
 * merged in at runtime by /api/models.
 */
const BASE_MODELS: Model[] = [
  // BS-RoFormer family
  {
    id: "bs_roformer_voc_hyperacev2",
    name: "BS-RoFormer Vocals HyperACE v2",
    shortName: "HyperACE v2",
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
    shortName: "HyperACE v2 Inst",
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
    shortName: "Resurrection Vocals",
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
    shortName: "Resurrection Inst",
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
    shortName: "PolarFormer Vocals",
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
    shortName: "Becruily Deux",
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
    shortName: "Flowers v10",
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
    shortName: "FV9",
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
    shortName: "FV8B",
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
    shortName: "Inst V1E",
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
    shortName: "MDX23C InstVoc HQ",
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
    shortName: "HTDemucs 4-Stem",
    arch: "HTDemucs",
    target: "4-stem",
    tags: ["drums", "bass", "vocals", "other"],
    sizeMB: 320,
    source: "facebookresearch/demucs",
    sdr: 11.4,
    stems: ["drums", "bass", "vocals", "other"],
    instrumentTargets: ["drums", "bass"],
  },

  // Additional HuggingFace-hosted checkpoints (verified in this workspace)
  {
    id: "mbr_instfv9_gabox",
    name: "Mel-Band RoFormer Inst Fv9 (Gabox)",
    shortName: "Inst FV9 Gabox",
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
    shortName: "Inst FV9-2 Gabox",
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
    shortName: "Becruily Deux",
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
    unsupported:
      "No download source is configured for this checkpoint, so it cannot be fetched.",
    name: "BS-RoFormer Inst HyperACE v2 (ckpt)",
    shortName: "HyperACE v2 Inst (ckpt)",
    arch: "BS-RoFormer",
    target: "instrumental",
    tags: ["clean", "low-bleed"],
    sizeMB: 289,
    source: "pcunwa/BS-Roformer-HyperACE",
    sdr: 12.1,
  },


  // Registry-backed models verified by probe (scripts/probe-registry-model.py)
  {
    id: "uvr_2hp",
    name: "2 HP UVR",
    shortName: "2 HP UVR",
    arch: "VR",
    cpuOk: true,
    target: "dual",
    tags: ["full band"],
    sizeMB: 121,
    source: "audio-separator model registry",
  },
  {
    id: "bs_roformer_voc_gabox",
    name: "BS-RoFormer Vocals (Gabox)",
    shortName: "Vocals Gabox",
    arch: "BS-RoFormer",
    target: "vocals",
    tags: ["fuller sound"],
    sizeMB: 610,
    source: "audio-separator model registry",
  },
  {
    id: "mbr_inst_v1e_plus",
    name: "Mel-Band RoFormer Inst V1E Plus",
    shortName: "Inst V1E Plus",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["low bleed"],
    sizeMB: 871,
    source: "audio-separator model registry",
  },
  {
    id: "mbr_inst_v2",
    name: "Mel-Band RoFormer Inst V2",
    shortName: "Inst V2",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["clean boundary"],
    sizeMB: 1502,
    source: "audio-separator model registry",
  },
  {
    id: "mbr_inst_3_gabox",
    name: "Mel-Band RoFormer Inst 3 (Gabox)",
    shortName: "Inst 3 Gabox",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["balanced"],
    sizeMB: 871,
    source: "audio-separator model registry",
  },
  {
    id: "mbr_fullness_v4",
    name: "Mel-Band RoFormer Fullness V4",
    shortName: "Fullness V4",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["fuller sound"],
    sizeMB: 871,
    source: "audio-separator model registry",
  },
  {
    id: "mbr_fullness_noise_v4",
    name: "Mel-Band RoFormer Fullness Noise V4",
    shortName: "Fullness Noise V4",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["noise reduction"],
    sizeMB: 871,
    source: "audio-separator model registry",
  },
  {
    id: "mbr_inst_fv8",
    name: "Mel-Band RoFormer Inst FV8",
    shortName: "Inst FV8",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["dual stems"],
    sizeMB: 871,
    source: "audio-separator model registry",
  },
  {
    id: "mbr_inst_fvx",
    name: "Mel-Band RoFormer Inst FVX",
    shortName: "Inst FVX",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["detailed split"],
    sizeMB: 871,
    source: "audio-separator model registry",
  },
  {
    id: "mbr_instv8",
    name: "Mel-Band RoFormer InstV8",
    shortName: "InstV8",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["stable stems"],
    sizeMB: 871,
    source: "audio-separator model registry",
  },
  {
    id: "mbr_instv8n",
    name: "Mel-Band RoFormer InstV8N",
    shortName: "InstV8N",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["breaths & tails"],
    sizeMB: 871,
    source: "audio-separator model registry",
  },
  {
    id: "mdx23c_instvoc_hq_2",
    name: "MDX23C InstVoc HQ 2",
    shortName: "MDX23C HQ 2",
    arch: "MDX23C",
    target: "dual",
    tags: ["high quality"],
    sizeMB: 428,
    source: "audio-separator model registry",
  },
  {
    id: "mdx23c_d1581",
    name: "MDX23C D1581",
    shortName: "MDX23C D1581",
    arch: "MDX23C",
    target: "dual",
    tags: ["balanced"],
    sizeMB: 175,
    source: "audio-separator model registry",
  },
  {
    id: "mbr_duality_v1",
    name: "Mel-Band RoFormer InstVoc Duality V1",
    shortName: "Duality V1",
    arch: "MelBand-RoFormer",
    target: "dual",
    tags: [],
    sizeMB: 0,
    source: "audio-separator model registry",
  },
  {
    id: "mbr_instvox_duality_v2",
    name: "Mel-Band RoFormer InstVox Duality V2",
    shortName: "InstVox Duality V2",
    arch: "MelBand-RoFormer",
    target: "dual",
    tags: [],
    sizeMB: 0,
    source: "audio-separator model registry",
  },

  // Registry-backed models verified by probe (scripts/probe-registry-model.py)
  {
    id: "htdemucs",
    name: "HTDemucs",
    shortName: "HTDemucs",
    arch: "HTDemucs",
    cpuOk: true,
    target: "4-stem",
    tags: ["balanced"],
    sizeMB: 80,
    stems: ["drums", "bass", "vocals", "other"],
    source: "audio-separator model registry",
    instrumentTargets: ["drums", "bass"],
  },
  {
    id: "hdemucs_mmi",
    name: "Hybrid Demucs (MMI)",
    shortName: "Hybrid Demucs",
    arch: "HybridDemucs",
    target: "4-stem",
    tags: ["detailed split"],
    sizeMB: 159,
    stems: ["drums", "bass", "vocals", "other"],
    source: "audio-separator model registry",
    // Verified broken here on 3 separate recordings; see models.json for the
    // full reason. Hidden from every picker rather than failing after upload.
    unsupported:
      "Produces non-finite samples on real audio here: inference completes but the stem write fails with 'Audio data must contain only finite values'. Verified on 3 separate recordings; the cached checkpoint was re-downloaded and is byte-for-byte the same size, so this is not corruption.",
  },
  {
    id: "htdemucs_6s",
    name: "HTDemucs 6-Source",
    shortName: "HTDemucs 6S",
    arch: "HTDemucs",
    cpuOk: true,
    target: "multi",
    tags: ["dual stems"],
    sizeMB: 52,
    stems: ["drums", "bass", "vocals", "guitar", "piano", "other"],
    source: "audio-separator model registry",
    instrumentTargets: ["drums", "bass", "guitar", "piano"],
  },

  // Registry-backed models verified by probe (scripts/probe-registry-model.py)
  {
    id: "mbr_vocals_center",
    name: "Mel-Band RoFormer Vocals",
    shortName: "Vocals",
    arch: "MelBand-RoFormer",
    target: "vocals",
    tags: ["balanced"],
    sizeMB: 870,
    stems: ["vocals", "other"],
    categories: ["Center"],
    source: "audio-separator model registry",
  },
  {
    id: "bs_roformer_male_female",
    name: "BS-RoFormer Male / Female",
    shortName: "Male / Female",
    arch: "BS-RoFormer",
    target: "vocals",
    tags: ["detailed split"],
    sizeMB: 502,
    stems: ["male", "female"],
    categories: ["Male/Female"],
    source: "audio-separator model registry",
  },
  {
    id: "bs_roformer_gender_ep267",
    name: "BS-RoFormer Male / Female (EP267)",
    shortName: "Male / Female EP267",
    arch: "BS-RoFormer",
    target: "vocals",
    tags: ["detailed split"],
    sizeMB: 502,
    stems: ["male", "female"],
    categories: ["Male/Female"],
    source: "audio-separator model registry",
  },
  {
    id: "mbr_crowd",
    name: "Mel-Band RoFormer Crowd",
    shortName: "Crowd",
    arch: "MelBand-RoFormer",
    target: "vocals",
    tags: ["noise reduction"],
    sizeMB: 870,
    stems: ["crowd", "other"],
    categories: ["Crowd"],
    source: "audio-separator model registry",
    repair: {
      categories: ["live-cleanup"],
      primaryStem: "Other",
      inputScope: "full-mix",
      preservesChannels: true,
    },
  },

  // Registry-backed models verified by probe (scripts/probe-registry-model.py)
  {
    id: "bs_roformer_viperx_1297",
    name: "BS-RoFormer Viperx 1297",
    shortName: "Viperx 1297",
    arch: "BS-RoFormer",
    target: "dual",
    tags: ["low bleed"],
    sizeMB: 609,
    stems: ["vocals", "instrumental"],
    categories: ["Center"],
    source: "audio-separator model registry",
  },
  {
    id: "bs_roformer_viperx_1296",
    name: "BS-RoFormer Viperx 1296",
    shortName: "Viperx 1296",
    arch: "BS-RoFormer",
    target: "dual",
    tags: ["stable stems"],
    sizeMB: 609,
    stems: ["vocals", "instrumental"],
    categories: ["Center"],
    source: "audio-separator model registry",
  },

  // Registry-backed models verified by probe (scripts/probe-registry-model.py)
  {
    id: "mbr_bleed_suppressor",
    name: "Mel-Band RoFormer Bleed Suppressor",
    shortName: "Bleed Suppress",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["low bleed"],
    sizeMB: 870,
    stems: ["bleed", "instrumental"],
    source: "audio-separator model registry",
    repair: {
      categories: ["denoise"],
      primaryStem: "Instrumental",
      inputScope: "full-mix",
      preservesChannels: true,
    },
  },
  {
    id: "mbr_metal_mesk",
    name: "Metal Inst (MESK)",
    shortName: "Metal Inst",
    arch: "MelBand-RoFormer",
    target: "instrumental",
    tags: ["detailed split"],
    sizeMB: 900,
    stems: ["vocals", "other"],
    source: "Hugging Face Politrees/UVR_resources",
  },
  {
    id: "mbr_bve_gonza",
    name: "Lead / Backing Vocals (Gonza)",
    shortName: "Lead / Backing",
    arch: "MelBand-RoFormer",
    target: "vocals",
    tags: ["stable stems"],
    sizeMB: 870,
    stems: ["lead", "back"],
    source: "Hugging Face Politrees/UVR_resources",
  },
  {
    id: "mbr_duality_aname",
    name: "Mel-Band RoFormer Duality V1 (Aname)",
    shortName: "Duality Aname",
    arch: "MelBand-RoFormer",
    target: "dual",
    tags: ["balanced"],
    sizeMB: 870,
    stems: ["vocals", "other"],
    source: "Hugging Face Politrees/UVR_resources",
  },

  // Registry-backed models verified by probe (scripts/probe-registry-model.py)
  {
    id: "mbr_guitar_becruily",
    name: "Guitar (becruily)",
    shortName: "Guitar",
    arch: "MelBand-RoFormer",
    cpuOk: true,
    target: "instrumental",
    tags: ["detailed split"],
    sizeMB: 41,
    stems: ["guitar", "other"],
    source: "Hugging Face Politrees/UVR_resources",
    instrumentTargets: ["guitar"],
  },

  // Registry-backed models verified by probe (scripts/probe-registry-model.py)

  // Registry-backed models verified by probe (scripts/probe-registry-model.py)
  {
    id: "drumsep_mdx23c",
    name: "DrumSep (MDX23C)",
    shortName: "DrumSep",
    arch: "MDX-C",
    target: "multi",
    tags: ["drum family detail"],
    sizeMB: 448,
    stems: ["kick", "snare", "toms", "hh", "ride", "crash"],
    instrumentTargets: ["kick", "snare", "toms", "hihat", "ride", "crash"],
    source: "audio-separator model registry",
  },
  {
    id: "htdemucs_ft",
    name: "HTDemucs Fine-Tuned",
    shortName: "HTDemucs FT",
    arch: "HTDemucs",
    target: "4-stem",
    tags: ["fine-tuned split"],
    sizeMB: 320,
    stems: ["drums", "bass", "vocals", "other"],
    instrumentTargets: ["drums", "bass"],
    source: "audio-separator model registry",
  },
  {
    id: "mdx_dereverb",
    name: "De-Reverb (MDX23C)",
    shortName: "De-Reverb",
    arch: "MDX-C",
    target: "dual",
    tags: ["reverb removal"],
    sizeMB: 448,
    stems: ["dry", "No dry"],
    categories: ["Dereverb"],
    source: "audio-separator model registry",
    repair: {
      categories: ["dereverb"],
      primaryStem: "Dry",
      inputScope: "full-mix",
      preservesChannels: true,
    },
  },
];

/**
 * Workbench trait shown on each model card.
 *
 * Traits are the primary way users choose between models that all "remove
 * vocals" but characteristically differ, so each one is a promise about the
 * output. New models should be assigned the trait that best describes them
 * rather than left to fall through to `tags[0]`, which produces traits that no
 * filter option can explain.
 */
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
  uvr_2hp: "Full band",
  bs_roformer_voc_gabox: "Fuller sound",
  mbr_inst_v1e_plus: "Low bleed",
  mbr_inst_v2: "Clean boundary",
  mbr_inst_3_gabox: "Balanced",
  mbr_fullness_v4: "Fuller sound",
  mbr_fullness_noise_v4: "Noise reduction",
  mbr_inst_fv8: "Dual stems",
  mbr_inst_fvx: "Detailed split",
  mbr_instv8: "Stable stems",
  mbr_instv8n: "Breaths & tails",
  mdx23c_instvoc_hq_2: "High quality",
  mdx23c_d1581: "Balanced",
  htdemucs: "Balanced",
  hdemucs_mmi: "Detailed split",
  htdemucs_6s: "Dual stems",
  mbr_vocals_center: "Balanced",
  bs_roformer_male_female: "Detailed split",
  bs_roformer_gender_ep267: "Detailed split",
  mbr_crowd: "Noise reduction",
  bs_roformer_viperx_1297: "Low bleed",
  bs_roformer_viperx_1296: "Stable stems",
  mbr_duality_v1: "Fuller sound",
  mbr_instvox_duality_v2: "Balanced",
  mbr_bleed_suppressor: "Low bleed",
  mbr_metal_mesk: "Detailed split",
  mbr_bve_gonza: "Stable stems",
  mbr_duality_aname: "Balanced",
  mbr_guitar_becruily: "Detailed split",
  drumsep_mdx23c: "Drum family detail",
  htdemucs_ft: "Fine-tuned split",
  mdx_dereverb: "Reverb removal",
};

export function modelTrait(m: Model): string {
  return TRAIT_BY_ID[m.id] ?? m.trait ?? m.tags[0] ?? "Balanced";
}

/**
 * Every trait currently used by at least one runnable model, with the number of
 * models carrying it.
 *
 * Derived from the catalog rather than a hand-written list on purpose: a
 * hard-coded option list inevitably offers traits no model has, producing a
 * filter that always returns zero results and reads as a broken picker. Adding a
 * model with a new trait is therefore enough to make a new filter appear.
 */
export function traitCounts(models: Model[]): { trait: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const m of models) {
    const trait = modelTrait(m);
    counts.set(trait, (counts.get(trait) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([trait, count]) => ({ trait, count }))
    .sort((a, b) => b.count - a.count || a.trait.localeCompare(b.trait));
}

/**
 * Plain-language explanation of what a trait means for the output, shown in the
 * model card's info popover. Keyed by trait because the guarantee belongs to the
 * trait ("low bleed always means low bleed"), not to one checkpoint.
 *
 * Wording is our own; the reference site's phrasing was not copied.
 */
export const TRAIT_DESCRIPTION: Record<string, string> = {
  "Low bleed":
    "Leaves the least vocal residue in the instrumental. Best when you want a clean backing track and will remix or cover over it.",
  "Stable stems":
    "Consistent output across songs and repeats. The safe default when you are not chasing a particular problem.",
  "Detailed split":
    "Preserves fine detail at the vocal/instrument boundary — reverb tails, breaths and doubled parts survive instead of being flattened.",
  "Fuller sound":
    "Keeps more of the original weight and sustain, at the cost of slightly more vocal bleed.",
  "Balanced":
    "An even trade-off between bleed and detail. Works well when you are unsure which characteristic matters for your track.",
  "Natural tone":
    "Aim for a result that does not sound processed — useful when the instrumental has to sit under a vocalist later.",
  "Dual stems":
    "Writes vocals and instrumental as separate files in one pass, rather than only returning the instrumental.",
  "High quality":
    "Trained for fidelity over speed. Slower, and worth it for a final render.",
  "Clean boundary":
    "Separates with minimal cross-contamination between stems, for material where the two sources overlap heavily.",
  "Full band":
    "Processes the entire spectrum rather than focusing on a band, which keeps very low and very high content intact.",
  "Noise reduction":
    "Targets hiss, hum and room tone instead of voices. Use when the problem is the recording, not the performance.",
  "Breaths & tails":
    "Keeps audible breaths and reverb tails on the vocal stem. Choose this when the vocal texture matters.",
  "Fallback":
    "The dependable option used when nothing else suits the material. Safe to default to.",
  "Multichannel":
    "Preserves channel differences for multichannel or wide-stereo source material.",
};

/** Description for a trait, with a safe fallback for traits not yet described. */
export function traitDescription(trait: string): string {
  return (
    TRAIT_DESCRIPTION[trait] ??
    `Separates with a "${trait.toLowerCase()}" character. Compare it against another model on the same file to hear the difference.`
  );
}

/**
 * Usage tiers present in a model list, with counts. A model with no `usage`
 * field is a single pass and reported as "1x".
 */
export function usageCounts(models: Model[]): { usage: UsageTier; count: number }[] {
  const counts = new Map<UsageTier, number>();
  for (const m of models) {
    const usage = m.usage ?? "1x";
    counts.set(usage, (counts.get(usage) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([usage, count]) => ({ usage, count }))
    .sort((a, b) => a.usage.localeCompare(b.usage));
}

/** The tier to display for a model. */
export function modelUsage(m: Model): UsageTier {
  return m.usage ?? "1x";
}

/** Ensemble presets — fuse multiple models (runs 2–6 model passes). */
const ENSEMBLE_PRESETS: Model[] = [
  {
    id: "ens_inst_avg_fft",
    name: "Inst · avg_fft",
    shortName: "Inst · avg_fft",
    arch: "Ensemble",
    target: "instrumental",
    tags: ["Balanced", "Ensemble"],
    sizeMB: 0,
    source: "ensemble",
    usage: "3x+",
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
    usage: "3x+",
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
    usage: "3x+",
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
    usage: "3x+",
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
    usage: "3x+",
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
    usage: "3x+",
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
    usage: "3x+",
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
    usage: "3x+",
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
    key: "instrument-extractor",
    label: "Instrument Extractor",
    short: "Instruments",
    description:
      "Pull a single instrument out of a full mix — drums, bass, guitar or piano — and get one file back.",
    icon: "target",
    // htdemucs_6s is the only model emitting all four instruments, so it is the
    // one default that never immediately restricts the picker.
    defaultModelId: "htdemucs_6s",
    // "instrumental" is included so the dedicated guitar model (target:
    // "instrumental") is offered alongside htdemucs_6s — the whole point of
    // this scene is Standard vs Dedicated for guitar. The instrumentTargets
    // filter in modelsForScene then keeps it out of the drums/bass/piano
    // lists, where it cannot apply.
    allowedTargets: ["4-stem", "multi", "instrumental"],
    instrument: true,
  },
  {
    key: "audio-repair",
    label: "Audio Repair",
    short: "Audio Repair",
    description:
      "Fix clicks, clipping, hum, hiss and uneven levels — corrective processing, not separation.",
    icon: "wrench",
    // Repair is ffmpeg DSP, not a model, so there is no default model and the
    // picker is hidden for this scene entirely.
    allowedTargets: [],
    repair: true,
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
    // Populated from the OBSERVED stems of the probe-verified models, not the
    // registry filenames — "chorus" in a filename turned out to emit
    // male/female, and the Category chip has to say what the tool actually does.
    subFilters: ["Center", "Male/Female", "Crowd"],
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
  const direct = SCENES.find((s) => s.key === key);
  if (direct) return direct;
  // Jobs persisted before the repair rebuild carry the old "denoise" key.
  // Falling through to SCENES[0] would label them "Vocal Remover", which is
  // worse than admitting they were a repair job.
  if (LEGACY_SCENE_ALIASES[key]) {
    return SCENES.find((s) => s.key === LEGACY_SCENE_ALIASES[key]) ?? SCENES[0];
  }
  return SCENES[0];
}

/** Scene keys that were renamed, so old stored jobs still resolve sensibly. */
const LEGACY_SCENE_ALIASES: Record<string, SceneKey> = {
  denoise: "audio-repair",
};

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
  /** Narrow an instrument scene to the models that emit this stem. */
  instrumentTarget?: string | null,
): Model[] {
  const meta = getScene(scene);
  return models.filter(
    (m) =>
      meta.allowedTargets.includes(m.target) &&
      // Models the backend cannot load (e.g. a custom architecture its
      // engine does not implement) are never offered for selection.
      !m.unsupported &&
      // An instrument scene can only offer models observed to emit a stem at
      // all, and — once one is chosen — only those that emit that stem. A
      // model here would be rejected by the worker after the upload, which is
      // exactly the late failure this scene exists to avoid.
      (!meta.instrument ||
        ((m.instrumentTargets?.length ?? 0) > 0 &&
          (!instrumentTarget ||
            (m.instrumentTargets ?? []).includes(instrumentTarget)))),
  );
}