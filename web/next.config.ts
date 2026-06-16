import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Hide the Next.js dev-tools button (the "N" in the corner) during demos. It is
  // dev-only UI - never shipped in a production build - so this just keeps the
  // screen clean while presenting.
  devIndicators: false,
};

export default nextConfig;
