export type SceneKey =
  | "vocal-remover"
  | "extract-vocals"
  | "karaoke"
  | "stem-splitter"
  | "denoise"
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

export interface Model {
  id: string;
  name: string;
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
  /** Number of model passes this preset runs ("1 pass" or "3+ passes"). */
  usage?: string;
  favorite?: boolean;
  recommended?: boolean;
  /** Ensemble preset (fuses multiple models). */
  ensemble?: boolean;
}

export type JobStatus = "queued" | "processing" | "ready" | "error";

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
}

export interface SceneMeta {
  key: SceneKey;
  label: string;
  short: string;
  description: string;
  icon: string;
  defaultModelId: string;
  allowedTargets: ModelTarget[];
  multiStem?: boolean;
}

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
  };
}

export interface CreateJobResponse {
  jobId: string;
  status: JobStatus;
  etaSec: number;
}