import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** POST /api/models/:id/cancel — cancel an in-flight model download. */
export async function POST(
  _req: NextRequest,
  { params }: { params: { id: string } },
) {
  try {
    const res = await fetch(`${API_URL}/api/models/${params.id}/cancel`, {
      method: "POST",
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to cancel download" },
      { status: 502 },
    );
  }
}