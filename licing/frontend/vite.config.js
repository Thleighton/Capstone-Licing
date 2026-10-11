import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo, /api se envía al backend Python (uvicorn en el puerto 8000).
// En Vercel, /api lo atiende api/index.py (ver vercel.json en la raíz).
// Con Docker, docker-compose.yml define BACKEND_URL y VITE_USE_POLLING.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": process.env.BACKEND_URL || "http://localhost:8000" },
    watch: process.env.VITE_USE_POLLING ? { usePolling: true, interval: 300 } : undefined,
  },
});
