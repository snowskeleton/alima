/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: { outDir: '../app/static/spa', emptyOutDir: true },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // Pages render inside a QueryClientProvider and a MemoryRouter; without
    // this the react-query devtools noise drowns the actual failures.
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'json-summary'],
      reportsDirectory: './coverage',
      // The entry point and generated type declarations have nothing to assert.
      exclude: ['src/main.tsx', 'src/**/*.d.ts', 'src/test/**', '**/node_modules/**'],
    },
  },
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
