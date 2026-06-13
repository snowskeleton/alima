import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: { outDir: '../app/static/spa', emptyOutDir: true },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/files': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/feed': 'http://localhost:8000',
      '/static': 'http://localhost:8000',
    },
  },
});
