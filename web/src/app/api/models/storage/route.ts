import { NextResponse } from "next/server";
import { jsonResponse } from "@/lib/http-json";

const API_URL = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** GET /api/models/storage — local model cache storage info. */
export async function GET(request: Request) {
  try {
    const res = await fetch(`${API_URL}/api/models/storage`, {
      cache: "no-store",
    });
    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }
    return jsonResponse(data, request);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to fetch storage" },
      { status: 502 },
    );
  }
}