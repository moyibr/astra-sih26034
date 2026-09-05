import type { NextConfig } from "next";

// Which commit this bundle was built from.
//
// Without it there is no way to tell, from the outside, whether a deployment
// carries a given change -- and Vercel serves prerendered pages from its edge
// cache for many minutes, so "I pushed it" and "it is live" can be far apart.
// That gap cost real time to argue about, twice. Now the page says.
//
// Vercel sets VERCEL_GIT_COMMIT_SHA during a build. Locally there is no such
// variable, so fall back to asking git, and to "dev" when even that fails
// (a source tarball, a container without git).
function buildSha(): string {
  if (process.env.VERCEL_GIT_COMMIT_SHA) {
    return process.env.VERCEL_GIT_COMMIT_SHA.slice(0, 7);
  }
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require("node:child_process")
      .execSync("git rev-parse --short HEAD", { cwd: __dirname, stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim();
  } catch {
    return "dev";
  }
}

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_BUILD_SHA: buildSha(),
  },
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
