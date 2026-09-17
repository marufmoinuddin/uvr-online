import { MODEL_CATALOG } from "@/lib/models";
import { toManagedModel } from "@/lib/models-api";
import { jsonResponse } from "@/lib/http-json";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * GET /api/models — model catalog.
 * Merges the seeded catalog with the worker's live models.json so newly
 * installed MSST models appear automatically.
 *
 * This is the largest API payload (~10 KB) and is polled by the workbench and
 * Explore pages, so it is served gzipped with an ETag: repeat polls become
 * empty 304s instead of re-transferring the whole catalog.
 */
export async function GET(request: Request) {
  try {
    const res = await fetch(`${API_URL}/api/models`, { cache: "no-store" });
    if (res.ok) {
      const live = await res.json();
      if (Array.isArray(live) && live.length > 0) {
        return jsonResponse(live, request);
      }
    }
  } catch {
    /* fall through to the seeded catalog */
  }
  // Worker unreachable — return the seeded catalog in ManagedModel shape so
  // consumers can safely read `.download.status` etc.
  return jsonResponse(MODEL_CATALOG.map(toManagedModel), request);
}