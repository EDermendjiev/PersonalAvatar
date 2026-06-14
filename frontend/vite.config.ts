import { defineConfig } from 'vite';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

// ESM-safe __dirname (package.json has "type": "module").
const __dirname = dirname(fileURLToPath(import.meta.url));

// Multi-page build: the visitor chat (index.html) and the admin dashboard
// (admin.html) are emitted as separate documents into dist/, alongside the
// shared dist/assets/** bundle. The FastAPI backend serves dist/index.html at
// "/" and dist/admin.html at "/admin" (see CONTRACT.md §8).
//
// During development the Vite dev server proxies "/api" to the FastAPI backend
// on :8000 so the SSE chat stream, config, conversation and admin endpoints all
// work without CORS.
export default defineConfig({
  appType: 'mpa',
  build: {
    target: 'es2022',
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        index: resolve(__dirname, 'index.html'),
        admin: resolve(__dirname, 'admin.html'),
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy the API (incl. the SSE chat stream) to the FastAPI backend in dev.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 4173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
