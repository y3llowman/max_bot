import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // "./" — сборка открывается с любого пути статического хостинга или из-под FastAPI.
  base: "./",
  plugins: [react()],
  // build/, а не dist/ — туда же собирает шаблон бэкенда: его Dockerfile берёт frontend/build.
  build: { outDir: "build", emptyOutDir: true },
  server: {
    host: true,
    port: 5173,
    // Разработка с локальным бэкендом: VITE_API_URL=/api, FastAPI на :8000.
    proxy: { "/api": "http://localhost:8000" },
  },
});
