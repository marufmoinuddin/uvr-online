import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * POST /api/jobs — create a separation job.
 * Forwards the multipart upload to the FastAPI GPU worker.
 */
export async function POST(req: NextRequest) {
  try {
    const form = await req.formData();
    // Pass the FormData body directly — fetch sets the correct multipart
    // boundary automatically. Do NOT forward the original Content-Type
    // (its boundary would not match the re-serialized body).
    const res = await fetch(`${API_URL}/api/jobs`, {
      method: "POST",
      body: form,
      duplex: "half",
    } as RequestInit);
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to create job" },
      { status: 502 },
    );
  }
}

/** GET /api/jobs — list all jobs (used by the polling fallback). */
export async function GET() {
  try {
    const res = await fetch(`${API_URL}/api/jobs`);
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to list jobs" },
      { status: 502 },
    );
  }
}