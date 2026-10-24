import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The gateway runs on a separate origin in dev (uvicorn on :8000). It already
// sends `Access-Control-Allow-Origin: *`, so the UI can call it directly via
// VITE_API_BASE_URL. We also expose a `/api` dev proxy as a CORS-free fallback:
// set VITE_API_BASE_URL=/api to route calls through Vite to the gateway.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
