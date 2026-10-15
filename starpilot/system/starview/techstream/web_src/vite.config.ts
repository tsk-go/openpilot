import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";

// StarView TechStream build: the page goes to ../web (techstream/web), which starviewd serves at /techstream/.
// The built files are committed (the comma has no Node). Rebuild after changing src/: npm ci && npm run build
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  base: "/techstream/",
  build: {
    outDir: "../web",
    emptyOutDir: true,
    assetsDir: "assets",
    // the tablet WebView is a current Chromium: no old-engine polyfills
    target: "es2022",
    sourcemap: false,
    rollupOptions: {
      output: {
        // content-hashed names: cached for good, index.html is served no-cache
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
  server: {
    // dev: proxy the API to a comma (STARVIEW_DEVICE=http://<comma>:8090)
    proxy: { "/api": { target: process.env.STARVIEW_DEVICE || "http://192.168.43.1:8090", changeOrigin: true } },
  },
});
