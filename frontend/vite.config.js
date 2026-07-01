import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During `vite dev` the API lives on :8000 (FastAPI). In production the built
// bundle is served by FastAPI itself on the same origin, so the proxy only
// matters for local development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "../backend/static",
    emptyOutDir: true,
  },
});
