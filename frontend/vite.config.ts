import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // dev-only: same-origin API so httpOnly cookies + CSRF work without CORS
      "/api": { target: "http://localhost:8000", changeOrigin: false },
    },
  },
});
