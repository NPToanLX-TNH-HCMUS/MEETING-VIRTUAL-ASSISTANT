import { defineConfig } from 'vite';

// Proxy keeps the UI same-origin with the backend, as the API contract assumes (no CORS).
const BACKEND = 'http://127.0.0.1:8000';

export default defineConfig({
  server: {
    proxy: {
      '/api': BACKEND,
      '/ws': { target: BACKEND.replace('http', 'ws'), ws: true },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
});
