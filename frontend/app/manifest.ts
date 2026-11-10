import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "EduCrew",
    short_name: "EduCrew",
    description: "Work log, maintenance tickets and class adjustment for faculty.",
    start_url: "/",
    display: "standalone",
    background_color: "#f7f5f0",
    theme_color: "#1f5c63",
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
