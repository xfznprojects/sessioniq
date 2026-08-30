import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": process.env.SESSIONIQ_API_TARGET ?? "http://127.0.0.1:8000",
      "/uploads": process.env.SESSIONIQ_API_TARGET ?? "http://127.0.0.1:8000"
    }
  }
});
