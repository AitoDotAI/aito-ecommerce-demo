import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  // In production, build a static export to `frontend/out/` so the
  // FastAPI backend can serve everything from a single port
  // (matches `aito-accounting-demo` + `aito-erp-demo`'s setup).
  // Dev keeps the proxy rewrite below so hot-reload + the running
  // FastAPI backend can share `localhost:8500` over Next's dev
  // server.
  ...(isDev ? {} : { output: "export" }),

  // Trailing slashes — for the static export `next build` writes
  // `/markdown/index.html` instead of `markdown.html`, which is
  // what `StaticFiles(html=True)` expects to resolve `/markdown/`.
  // Skip the redirect so the FastAPI proxy below sees `/api/*` in
  // whichever form the client sent (avoids 308 ↔ 307 ping-pong).
  // Dev only: Next blocks its dev resources (and with them hydration) for any origin but localhost. To open the dev server
  // from another device, name the host: NEXT_DEV_ORIGINS=192.168.1.20 ./do dev. Unset, nothing changes.
  ...(isDev ? { allowedDevOrigins: (process.env.NEXT_DEV_ORIGINS ?? "").split(",").map((h) => h.trim()).filter(Boolean) } : {}),

  trailingSlash: true,
  skipTrailingSlashRedirect: true,

  // Dev only: proxy API calls to the FastAPI backend so dev keeps
  // same-origin behaviour (no CORS, cookies survive). In prod the
  // static export is served from the backend port directly, so
  // the rewrite isn't needed.
  ...(isDev
    ? {
        async rewrites() {
          return [
            {
              source: "/api/:path*",
              destination: `http://localhost:${process.env.PORT_BACKEND ?? "8501"}/api/:path*`,
            },
          ];
        },
      }
    : {}),
};

export default nextConfig;
