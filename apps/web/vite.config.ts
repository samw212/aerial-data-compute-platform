import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.ADCP_API ?? "http://127.0.0.1:8000", changeOrigin: true },
      "/ws": { target: process.env.ADCP_API ?? "http://127.0.0.1:8000", ws: true, changeOrigin: true },
      "/tiles": { target: process.env.ADCP_API ?? "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: {
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          three: ["three", "@react-three/fiber", "@react-three/drei"],
          map: ["maplibre-gl"],
        },
      },
    },
  },
  worker: { format: "es" },
  test: { environment: "jsdom", include: ["src/**/*.test.ts", "src/**/*.test.tsx"] },
});
