import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "VITE_");
  return {
    base: env.VITE_PORTAL_BASE || "/",
    plugins: [react()],
    server: { port: 5174, strictPort: true, proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } } },
  };
});
