/**
 * Fetch what the Audio Repair scene may offer: the ffmpeg operations AND the
 * neural repair models, with their categories.
 *
 * Deliberately fetched rather than bundled, for the same reason the instrument
 * list is: eligibility is decided by each model's declared `repair` capability
 * in `api/models.json`. A copy in the frontend would keep offering a model the
 * worker refuses, or hide one that works, and the user would find out only
 * after uploading.
 */
export interface RepairOperationsResponse {
  operations: {
    id: string;
    label: string;
    description: string;
    requiresGpu: boolean;
  }[];
  models: {
    id: string;
    name: string;
    shortName: string;
    arch: string;
    categories: string[];
    primaryStem: string | null;
    inputScope: string | null;
    preservesChannels: boolean;
    requiresGpu: boolean;
    outputLabel: string;
  }[];
  categories: { key: string; label: string; models: string[] }[];
  formats: string[];
}

export async function fetchRepairCapabilities(): Promise<RepairOperationsResponse> {
  const res = await fetch("/api/repair/capabilities");
  if (!res.ok) {
    throw new Error(`worker responded ${res.status}`);
  }
  const body = (await res.json()) as Partial<RepairOperationsResponse>;
  return {
    operations: body.operations ?? [],
    models: body.models ?? [],
    categories: body.categories ?? [],
    formats: body.formats ?? ["wav"],
  };
}