import { defineConfig } from '@playwright/test'

// End-to-end smoke and accessibility tests against a running stack (docker compose or vite preview).
// E2E_BASE_URL defaults to the compose frontend; PW_CHANNEL=msedge reuses an installed browser locally.
export default defineConfig({
  testDir: 'e2e',
  globalSetup: './e2e/global-setup.js',
  outputDir: 'e2e/.results',
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:5173',
    channel: process.env.PW_CHANNEL || undefined,
    trace: 'retain-on-failure',
  },
})
