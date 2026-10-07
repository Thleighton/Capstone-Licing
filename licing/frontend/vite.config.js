import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo, /api se envía al backend Python (uvicorn en el puerto 8000).
// En Vercel, /api lo atiende api/index.py (ver vercel.json en la raíz).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
