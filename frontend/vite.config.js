import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// In development the API is proxied to the Spring Boot backend, so the browser talks to one origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.VITE_PROXY_TARGET || 'http://localhost:8080', changeOrigin: true } },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{js,jsx}'],   // e2e/*.spec.js are Playwright tests (npm run test:e2e)
    setupFiles: ['./src/test/setup.js'],
    css: false,
  },
})
