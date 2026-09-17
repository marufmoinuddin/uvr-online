import { NextRequest } from "next/server";

const API_URL =
  process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

/**
 * GET /api/jobs/[id]/download — stream the zip bundle of a job's stems.
 *
 * The UI links to this same-origin path, so it needs a proxy route or the
 * download 404s. Streamed through without buffering so large bundles do not
 * sit in memory, and `content-disposition` is preserved so the browser saves
 * a properly named file.
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  const search = new URL(req.url).search;
  const target = `${API_URL}/api/jobs/${encodeURIComponent(params.id)}/download${search}`;

  let res: Response;
  try {
    res = await fetch(target, { cache: "no-store" });
  } catch (err) {
    return new Response(
      JSON.stringify({
        error: err instanceof Error ? err.message : "worker unreachable",
      }),
      { status: 502, headers: { "content-type": "application/json" } },
    );
  }

  const out = new Headers();
  for (const h of [
    "content-type",
    "content-length",
    "content-disposition",
  ]) {
    const v = res.headers.get(h);
    if (v) out.set(h, v);
  }

  if (res.status >= 400) {
    return new Response(null, { status: res.status, headers: out });
  }

  return new Response(res.body, { status: res.status, headers: out });
}
