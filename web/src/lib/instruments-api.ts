import type { InstrumentTarget } from "@/components/scenes/instrument-picker";

/**
 * Fetch the instruments the catalogue can actually isolate.
 *
 * Deliberately fetched rather than bundled, for the same reason the repair
 * list is: the set is derived from each model's OBSERVED output stems in
 * `api/models.json`. A hardcoded copy in the frontend would keep offering an
 * instrument no model can produce, and the user would only find out after
 * uploading their file.
 */
export async function fetchInstruments(): Promise<InstrumentTarget[]> {
  const res = await fetch("/api/instruments");
  if (!res.ok) {
    throw new Error(`worker responded ${res.status}`);
  }
  const body = (await res.json()) as { targets?: InstrumentTarget[] };
  return body.targets ?? [];
}