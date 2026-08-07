import { defineConfig } from "vite";

const djangoPort = process.env.DJANGO_PORT || "8001";
const djangoHost = process.env.DJANGO_HOST || "127.0.0.1";

export default defineConfig({
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
