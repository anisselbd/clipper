import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Export statique : l'app est 100% client, donc empaquetable dans Tauri
  // (charge depuis app/out). N'affecte pas `next dev`.
  output: "export",
  images: { unoptimized: true },
};

export default nextConfig;
