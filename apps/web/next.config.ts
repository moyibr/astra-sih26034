import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits a self-contained server bundle with only the modules actually
  // imported, which is what the Docker runner stage copies. Without it the
  // production image has to carry the whole of node_modules.
  //
  // Vercel produces its own output and does not need this, so it is switched
  // off there rather than built and thrown away.
  output: process.env.VERCEL ? undefined : "standalone",
  // The repo is a monorepo, so tell Next where the workspace actually starts;
  // otherwise it infers a root from the nearest lockfile and traces the wrong
  // files into the standalone bundle.
  outputFileTracingRoot: __dirname,
  images: {
    // Evidence images are served straight from the API and are already sized
    // for display; putting them through the optimiser adds a hop and a cache
    // for no gain.
    unoptimized: true,
  },
};

export default nextConfig;
