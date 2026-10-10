import { NextResponse } from "next/server";

const API_INTERNAL =
  process.env.API_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Proxy for the worker's instrument list.
 *
 * Same-origin so the browser never talks to :8000 directly — that keeps it
 * behind the Next proxy like every other API call.
 */
export async function GET() {
  try {
    const res = await fetch(`${API_INTERNAL}/api/instruments`, {
      cache: "no-store",
    });
    if (!res.ok) {
      return NextResponse.json(
        { detail: `worker responded ${res.status}` },
        { status: 502 },
      );
    }
    const body = await res.json();
    return NextResponse.json(body);
  } catch {
    return NextResponse.json(
      { detail: "Could not reach the worker." },
      { status: 503 },
    );
  }
}