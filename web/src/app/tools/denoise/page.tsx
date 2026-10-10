import { redirect, permanentRedirect } from "next/navigation";

/**
 * The scene used to be called "denoise" and was really a separation model.
 * It is now a genuine repair pipeline at /tools/audio-repair.
 *
 * Permanent redirect so existing bookmarks and any shared links keep working
 * rather than 404ing.
 */
export default function LegacyDenoisePage() {
  permanentRedirect("/tools/audio-repair");
}