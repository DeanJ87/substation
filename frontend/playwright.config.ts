// End-to-end and accessibility tests against a running SubStation (Compose stack or dev servers).
//   SUBSTATION_E2E_URL=http://localhost:8088 npx playwright test
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.SUBSTATION_E2E_URL ?? 'http://localhost:8088',
    viewport: { width: 1400, height: 900 },
    trace: 'retain-on-failure',
  },
})
