/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the Django server runs on :8000; Vite proxies the API, auth and event stream to it.
const backend = process.env.SUBSTATION_BACKEND_URL ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: backend, changeOrigin: false },
      '/_allauth': { target: backend, changeOrigin: false },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: true,
    // 005-DR-29: CI fails if coverage of the whole app (not just the files tests touch) drops below today's floor;
    // raise these as tests are added, never lower them
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.test.*', 'src/api/**', 'src/test/**'],
      reporter: ['text-summary'],
      thresholds: { statements: 4, branches: 3, functions: 2, lines: 4 },
    },
  },
})
