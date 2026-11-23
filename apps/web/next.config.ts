import type { NextConfig } from "next";

const apiOrigin = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
const isDev = process.env.NODE_ENV !== "production";

// Next.js App Router emits inline bootstrap scripts, so 'unsafe-inline' is required for scripts unless a
// nonce-based middleware is added (tracked in docs/KNOWN_LIMITATIONS.md). All data is rendered as text by React.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  // Dev server only: hosts (e.g. your PC's LAN IP) allowed to load the app from other devices on the network.
  allowedDevOrigins: process.env.DEV_ALLOWED_ORIGINS?.split(",").map((h) => h.trim()).filter(Boolean),
  // Same-origin API: the browser talks to /api/v1 on the web origin, so session cookies stay first-party.
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${apiOrigin}/api/v1/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
