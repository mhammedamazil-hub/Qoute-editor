import { defineConfig } from "vite";

// The engine is a standalone static app. Scenes are served from public/scenes; no backend.
export default defineConfig({
  base: "./",
  server: {
    host: "0.0.0.0",          // reachable from the sandbox preview
    port: 5180,
    strictPort: false,
    allowedHosts: true,       // the preview host name is not known in advance
  },
  preview: {
    host: "0.0.0.0",
    port: 4180,
    allowedHosts: true,
  },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 1200,
  },
});
