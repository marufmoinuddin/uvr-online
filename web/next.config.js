/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  images: {
    remotePatterns: [{ protocol: "https", hostname: "**" }],
  },
  // Verification builds into its OWN directory so it never collides with a
  // running development or production server, which both share `.next` with
  // the default build. Without this the gate has to stop those processes to
  // build, and stopping a process the gate does not own is exactly the kind of
  // side effect a verification run must not have.
  //
  // `UVR_NEXT_DIST_DIR` is ours, not a Next.js switch. Scripts/verify-web.sh
  // sets it; normal development leaves it unset and keeps using `.next`.
  distDir: process.env.UVR_NEXT_DIST_DIR || ".next",
};

module.exports = nextConfig;