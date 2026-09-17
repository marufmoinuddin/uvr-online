import { NextResponse } from "next/server";

const API_URL = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** GET /api/health — GPU + queue status from the worker. */
export async function GET() {
  try {
    const res = await fetch(`${API_URL}/api/health`, { cache: "no-store" });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { gpu: false, queueDepth: 0, device: "unknown", error: "worker unreachable" },
      { status: 200 },
    );
  }
}