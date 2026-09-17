import { NextRequest, NextResponse } from "next/server";
import { jsonResponse } from "@/lib/http-json";

const API_URL = process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

/** GET /api/jobs — list all jobs (used by the polling fallback).
 *
 * Served with an ETag so an unchanged job list revalidates to an empty 304
 * instead of re-sending the full list on every poll. `no-cache` forces
 * revalidation, so progress updates are never served stale.
 */
export async function GET(request: Request) {
  try {
    const res = await fetch(`${API_URL}/api/jobs`);
    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status });
    }
    return jsonResponse(data, request);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to list jobs" },
      { status: 502 },
    );
  }
}

/** DELETE /api/jobs — clear finished jobs from the worker's console. */
export async function DELETE() {
  try {
    const res = await fetch(`${API_URL}/api/jobs`, { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to clear jobs" },
      { status: 502 },
    );
  }
}