import type { EnsembleMode, JobStem } from "./types";

/**
 * Ensemble engine — client-side types + helpers. The heavy lifting
 * (phase-aligned FFT/waveform fusion) runs on the API worker; this module
 * mirrors the contract and provides the builder UI helpers.
 */

export const ENSEMBLE_MODES: {
  id: EnsembleMode;
  label: string;
  description: string;
}[] = [
  {
    id: "avg_fft",
    label: "Average (FFT)",
    description: "Mean of complex spectra — balanced, low artifacts.",
  },
  {
    id: "median_fft",
    label: "Median (FFT)",
    description: "Per-bin median — removes outliers, very clean.",
  },
  {
    id: "max_fft",
    label: "Max (FFT)",
    description: "Per-bin max magnitude — aggressive, keeps detail.",
  },
  {
    id: "min_fft",
    label: "Min (FFT)",
    description: "Per-bin min magnitude — conservative, low bleed.",
  },
  {
    id: "avg_wave",
    label: "Average (Wave)",
    description: "Time-domain mean — fastest, phase preserved.",
  },
  {
    id: "median_wave",
    label: "Median (Wave)",
    description: "Time-domain median — robust to single-model spikes.",
  },
];

export interface EnsembleMember {
  jobId: string;
  modelId: string;
  modelName: string;
  weight: number;
}

export interface EnsemblePlan {
  members: EnsembleMember[];
  mode: EnsembleMode;
  targetStem: string;
}

export function defaultPlan(): EnsemblePlan {
  return {
    members: [],
    mode: "avg_fft",
    targetStem: "vocals",
  };
}

export function normalizeWeights(members: EnsembleMember[]): number[] {
  const total = members.reduce((acc, m) => acc + m.weight, 0) || 1;
  return members.map((m) => m.weight / total);
}

export function validatePlan(plan: EnsemblePlan): string | null {
  if (plan.members.length < 2) {
    return "Select at least 2 models to ensemble.";
  }
  if (plan.members.length > 6) {
    return "Maximum 6 models per ensemble.";
  }
  return null;
}

/** Placeholder for the fused result shape returned by POST /api/ensemble */
export interface EnsembleResult {
  jobId: string;
  mode: EnsembleMode;
  stems: JobStem[];
  memberStems: Record<string, JobStem[]>;
}