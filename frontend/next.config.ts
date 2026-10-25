import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Forward /api calls to the FastAPI backend during `npm run dev`.
  // In production, Caddy sends /api straight to FastAPI before it reaches Next.js.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
    ];
  },
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
