import { defineConfig } from "vite";
import { resolve } from "node:path";

const djangoPort = process.env.DJANGO_PORT || "8001";
const djangoHost = process.env.DJANGO_HOST || "127.0.0.1";

export default defineConfig({
  build: {
    rollupOptions: {
      // Dua halaman: dashboard dan detail output.
      input: {
        main: resolve(__dirname, "index.html"),
        detail: resolve(__dirname, "detail.html"),
      },
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: `http://${djangoHost}:${djangoPort}`,
        changeOrigin: true,
      },
    },
  },
});
