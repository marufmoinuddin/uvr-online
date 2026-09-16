import { NextResponse } from "next/server";
import { MODEL_CATALOG } from "@/lib/models";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * GET /api/models — model catalog.
 * Merges the seeded catalog with the worker's live models.json so newly
 * installed MSST models appear automatically.
 */
export async function GET() {
  try {
    const res = await fetch(`${API_URL}/api/models`, { cache: "no-store" });
    if (res.ok) {
      const live = await res.json();
      if (Array.isArray(live) && live.length > 0) {
        return NextResponse.json(live);
      }
    }
  } catch {
    /* fall through to the seeded catalog */
  }
  return NextResponse.json(MODEL_CATALOG);
}