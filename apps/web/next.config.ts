import path from "node:path";
import type { NextConfig } from "next";

const apiTarget = (process.env.API_PROXY_TARGET ?? "http://localhost:8000").replace(/\/$/, "");
const crossOriginIsolation = process.env.CROSS_ORIGIN_ISOLATION !== "false";

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname, "../../"),
  reactStrictMode: true,
  typedRoutes: true,
  experimental: {
    // Bodies forwarded through the /api rewrite are capped at 10 MB by
    // default, which drops ROM uploads and large save states (PPSSPP states
    // are ~40 MB). Match the API's MAX_ROM_UPLOAD_BYTES default.
    proxyClientMaxBodySize: "2gb",
  },
  // The browser only ever talks to this origin; /api is forwarded server-side.
  // That keeps ROM streaming same-origin, which COEP requires.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiTarget}/api/:path*` }];
  },
  async headers() {
    if (!crossOriginIsolation) return [];
    // Required for SharedArrayBuffer (threaded emulator cores). Every asset the
    // pages load is same-origin, so require-corp is safe.
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          { key: "Cross-Origin-Embedder-Policy", value: "require-corp" },
        ],
      },
    ];
  },
};

export default nextConfig;
