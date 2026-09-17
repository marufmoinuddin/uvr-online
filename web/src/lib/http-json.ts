import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";

/**
 * JSON responses for route handlers, with the caching/compression that
 * Next.js does NOT apply to `route.ts` handlers automatically.
 *
 * Next.js compresses and caches prerendered pages, but responses built with
 * `NextResponse.json()` are sent uncompressed with no validators. `/api/models`
 * is ~10.7 KB and is polled by the workbench and Explore pages, so those polls
 * re-sent the whole catalog every time.
 *
 * This helper adds three things:
 *   1. gzip when the client accepts it and the body is worth compressing,
 *   2. a weak ETag so repeat polls can revalidate,
 *   3. `Cache-Control: private, no-cache` — the response may be stored, but
 *      MUST be revalidated before every reuse. That keeps data fresh (no stale
 *      reads) while turning repeat polls into empty 304s.
 *
 * Safety: nothing is cached without revalidation, so personalized or
 * fast-changing data (job progress, install state) can never be served stale.
 */

/** Below this size gzip overhead outweighs the saving. */
const MIN_GZIP_BYTES = 1024;

function etagFor(body: string): string {
  const digest = createHash("sha1").update(body).digest("base64url");
  return `W/"${digest}"`;
}

/** True when any candidate in `If-None-Match` matches our ETag (weak compare). */
function ifNoneMatch(header: string | null, etag: string): boolean {
  if (!header) return false;
  if (header.trim() === "*") return true;
  const target = etag.replace(/^W\//, "");
  return header
    .split(",")
    .map((v) => v.trim().replace(/^W\//, ""))
    .some((v) => v === target);
}

export function jsonResponse(
  data: unknown,
  request?: Request,
  init?: { status?: number },
): Response {
  const body = JSON.stringify(data);
  const status = init?.status ?? 200;
  const etag = etagFor(body);

  const base: Record<string, string> = {
    "Content-Type": "application/json; charset=utf-8",
    // Store, but always revalidate — never serve stale data.
    "Cache-Control": "private, no-cache",
    ETag: etag,
    Vary: "Accept-Encoding",
  };

  // Fast path: the client already has this exact representation.
  if (ifNoneMatch(request?.headers.get("if-none-match") ?? null, etag)) {
    return new Response(null, { status: 304, headers: base });
  }

  const buf = Buffer.from(body, "utf8");
  const acceptsGzip = /\bgzip\b/i.test(request?.headers.get("accept-encoding") ?? "");

  if (acceptsGzip && buf.byteLength >= MIN_GZIP_BYTES) {
    const gzipped = gzipSync(buf);
    // Only use compression when it actually helps.
    if (gzipped.byteLength < buf.byteLength) {
      return new Response(gzipped, {
        status,
        headers: { ...base, "Content-Encoding": "gzip" },
      });
    }
  }

  return new Response(buf, {
    status,
    headers: { ...base, "Content-Length": String(buf.byteLength) },
  });
}
