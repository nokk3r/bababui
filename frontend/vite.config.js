import path from "node:path";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

const root = path.dirname(fileURLToPath(import.meta.url));

/* Локали и иконки лежат в static/: бэкенд читает те же локали, в сборку они попадают как есть. */
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  base: "/static/",
  publicDir: "../static",
  resolve: {
    alias: { "@": path.resolve(root, "src") },
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8080" },
  },
});
