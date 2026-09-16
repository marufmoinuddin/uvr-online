import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** POST /api/jobs/:id/cancel — cancel a queued or processing job. */
export async function POST(
  _req: NextRequest,
  { params }: { params: { id: string } },
) {
  try {
    const res = await fetch(`${API_URL}/api/jobs/${params.id}/cancel`, {
      method: "POST",
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to cancel job" },
      { status: 502 },
    );
  }
}