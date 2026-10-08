import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

const api = process.env.SHOWTIME_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: api, changeOrigin: false } },
    watch: { ignored: ["**/node_modules/**", "**/dist/**"] },
  },
  preview: { proxy: { "/api": { target: api } } },
  worker: { format: "es" }, // MapLibre's tile worker is an ES module
  build: {
    target: "es2022",
    sourcemap: false,
    chunkSizeWarningLimit: 2500,
    rollupOptions: {
      output: {
        manualChunks: {
          three: ["three", "@react-three/fiber", "@react-three/drei", "@react-three/postprocessing", "postprocessing"],
          react: ["react", "react-dom", "react-router"],
          charts: ["recharts"],
          flow: ["@xyflow/react"],
        },
      },
    },
  },
  test: { environment: "jsdom", include: ["src/**/*.test.ts", "src/**/*.test.tsx"] },
} as never);
