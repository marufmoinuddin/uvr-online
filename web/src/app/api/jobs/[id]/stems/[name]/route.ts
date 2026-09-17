import { NextRequest } from "next/server";

const API_URL =
  process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

/**
 * GET /api/jobs/[id]/stems/[name] — stream a result stem.
 *
 * Each job stores same-origin stem URLs, so the browser asks THIS origin for
 * them. Without this route those requests 404 and the audio element has
 * nothing to play.
 *
 * Bytes are streamed straight through rather than buffered, and the Range
 * header is forwarded so the browser can seek (and so it gets the 206 it
 * expects when scrubbing).
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { id: string; name: string } },
) {
  const target =
    `${API_URL}/api/jobs/${encodeURIComponent(params.id)}` +
    `/stems/${encodeURIComponent(params.name)}`;

  const forwarded: Record<string, string> = {};
  const range = req.headers.get("range");
  if (range) forwarded["range"] = range;

  let res: Response;
  try {
    res = await fetch(target, { headers: forwarded, cache: "no-store" });
  } catch (err) {
    return new Response(
      JSON.stringify({
        error: err instanceof Error ? err.message : "worker unreachable",
      }),
      { status: 502, headers: { "content-type": "application/json" } },
    );
  }

  // Pass through the media headers the player cares about.
  const out = new Headers();
  for (const h of [
    "content-type",
    "content-length",
    "content-range",
    "accept-ranges",
    "last-modified",
    "etag",
  ]) {
    const v = res.headers.get(h);
    if (v) out.set(h, v);
  }
  if (!out.has("accept-ranges")) out.set("accept-ranges", "bytes");

  // 404/410 etc. carry no useful body here.
  if (res.status >= 400) {
    return new Response(null, { status: res.status, headers: out });
  }

  return new Response(res.body, { status: res.status, headers: out });
}
