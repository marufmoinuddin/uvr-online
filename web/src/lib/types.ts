export type SceneKey =
  | "vocal-remover"
  | "extract-vocals"
  | "karaoke"
  | "stem-splitter"
  | "instrument-extractor"
  | "audio-repair"
  | "acapella"
  | "vocal-tools"
  | "production"
  | "model-picker";

export type ModelTarget =
  | "vocals"
  | "instrumental"
  | "dual"
  | "4-stem"
  | "multi";

/**
 * Multiplier shown on a model card and used by the Usage filter. Mirrors the
 * reference site ("1x", "2x", "3x+") rather than the old "1 pass"/"3+ passes"
 * phrasing, which read as a sentence rather than a cost.
 */
export type UsageTier = "1x" | "2x" | "3x+";

/**
 * Repair capabilities a model may declare.
 *
 * This is deliberately NOT derived from `target`: being `dual` or `instrumental`
 * says nothing about whether a model performs a repair. Eligibility is its own
 * field so the Audio Repair scene can never offer a separation model that
 * cannot actually repair.
 */
export type NeuralRepairCategory =
  | "denoise"
  | "dereverb"
  | "live-cleanup"
  | "enhance";

export interface RepairCapability {
  categories: NeuralRepairCategory[];
  /**
   * The stem that holds the REPAIRED audio, chosen by measuring each output
   * against a known-clean reference (scripts/test-repair-models.py) — never by
   * guessing, and never outputs[0]. A model emitting two files does not tell you
   * which one is the repair.
   */
  primaryStem: string;
  /** What the model expects to be fed. */
  inputScope: "full-mix" | "vocals" | "instrumental" | "speech";
  /** Measured: true when the output keeps the source channel count. */
  preservesChannels: boolean;
}

export interface Model {
  id: string;
  name: string;
  /** Compact name for dense grids, e.g. "Becruily Deux". Falls back to `name`. */
  shortName?: string;
  arch: string;
  target: ModelTarget;
  tags: string[];
  sizeMB: number;
  source: string;
  /** Verified upstream license (see lib/licenses.ts). */
  license?: string;
  sdr?: number;
  installed?: boolean;
  stems?: string[];
  description?: string;
  /** Workbench trait shown on the model card (e.g. "Low bleed"). */
  trait?: string;
  /** Scene sub-filter buckets this model belongs to (e.g. "Center"). */
  categories?: string[];
  /**
   * How many model passes this preset runs, using the reference site's
   * vocabulary: "1x", "2x" or "3x+". Undefined means a single pass.
   */
  usage?: UsageTier;
  favorite?: boolean;
  recommended?: boolean;
  /** Ensemble preset (fuses multiple models). */
  ensemble?: boolean;
  /**
   * Set when this model cannot be run by the current backend, holding the
   * reason. Such models are hidden from the workbench picker so users never
   * hit a failure they cannot act on.
   */
  unsupported?: string | null;
  /**
   * Instrument stems this model has been OBSERVED to emit, used by the
   * Instrument Extractor scene. Populated from probe output filenames, never
   * from the checkpoint's advertised capabilities — a model offering "piano"
   * that never writes a Piano stem must not appear in the piano list.
   */
  instrumentTargets?: string[];
  /**
   * Present only when this model has been verified to perform a neural repair.
   * Drives Audio Repair eligibility; see `RepairCapability`.
   */
  repair?: RepairCapability;
}

export type JobStatus = "queued" | "processing" | "ready" | "error" | "cancelled";

export type JobStage = "queued" | "uploading" | "gpu" | "assemble" | "done";

export interface JobStem {
  name: string;
  url: string;
  sizeBytes: number;
  format: string;
}

export interface Job {
  id: string;
  status: JobStatus;
  scene: SceneKey;
  modelId: string;
  fileName: string;
  progress: number; // 0-100
  stage: JobStage;
  etaSec?: number;
  createdAt: number;
  resultStems?: JobStem[];
  downloadUrls?: string[];
  error?: string;
  cancelled?: boolean;
}

export interface SceneMeta {
  key: SceneKey;
  label: string;
  short: string;
  description: string;
  icon: string;
  /**
   * Model preselected when entering the scene. Omitted by repair scenes,
   * which run ffmpeg DSP and have no model at all.
   */
  defaultModelId?: string;
  allowedTargets: ModelTarget[];
  multiStem?: boolean;
  /**
   * True when this scene repairs the recording instead of separating it.
   * Repair scenes show an operation picker and hide the model grid.
   */
  repair?: boolean;
  /**
   * True when this scene isolates ONE instrument stem from a multi-stem
   * model. Such scenes show an instrument picker alongside the model grid and
   * require a target before processing.
   */
  instrument?: boolean;
  /**
   * Optional categories this scene offers as a sub-filter (the reference's
   * Vocal Tools "Center / Male-Female" split). When set, the workbench shows
   * one filter chip per category and keeps only models tagged with it.
   *
   * Scenes that declare categories but whose models carry none render an
   * explicit empty state rather than silently showing nothing.
   */
  subFilters?: string[];
}

/** Model categories usable as a scene sub-filter. */
export const MODEL_CATEGORIES = [
  "Center",
  "Male/Female",
] as const;

export type ModelCategory = (typeof MODEL_CATEGORIES)[number];

export interface AppState {
  jobs: Job[];
  activeJobId: string | null;
  modelCatalog: Model[];
  selectedModelId: string;
  scene: SceneKey;
  theme: "light" | "dark" | "system";
}

export interface HealthInfo {
  gpu: boolean;
  gpuName?: string;
  vramFreeMb?: number;
  queueDepth: number;
  device: string;
}

export type EnsembleMode =
  | "avg_fft"
  | "median_fft"
  | "max_fft"
  | "min_fft"
  | "avg_wave"
  | "median_wave";

export interface EnsembleRequest {
  jobIds: string[];
  mode: EnsembleMode;
  weights?: number[];
}

export interface CreateJobRequest {
  scene: SceneKey;
  modelId: string;
  options: {
    outputFormat: "wav" | "flac" | "mp3";
    mp3BitRate?: string;
    extractInstrumental?: boolean;
    useTTA?: boolean;
    stemSelection?: string[];
    /** Instrument stem to keep, e.g. "guitar". Instrument Extractor scene. */
    extractTarget?: string;
    /** Repair operations to apply in worker order. Audio Repair scene. */
    repairOps?: string[];
  };
}

export interface CreateJobResponse {
  jobId: string;
  status: JobStatus;
  etaSec: number;
}