import { NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** GET /api/models/storage — local model cache storage info. */
export async function GET() {
  try {
    const res = await fetch(`${API_URL}/api/models/storage`, {
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to fetch storage" },
      { status: 502 },
    );
  }
}