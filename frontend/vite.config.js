import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

/* Локали и иконки лежат в static/: бэкенд читает те же локали, в сборку они попадают как есть. */
export default defineConfig({
  plugins: [vue()],
  base: "/static/",
  publicDir: "../static",
  server: {
    proxy: { "/api": "http://127.0.0.1:8080" },
  },
});
