import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end configuration.
 *
 * These tests drive a real browser against a real FastAPI server backed by a
 * real (throwaway) database. That is the point: they are the only layer that
 * can catch the SPA and the API disagreeing about a contract, which neither
 * side's own tests can see.
 *
 * Keep this suite small and stable. It is the slowest layer and the one that
 * rots fastest, so it covers the handful of flows that must never break rather
 * than trying to reach the coverage the unit suites already provide.
 */

const PORT = Number(process.env.E2E_PORT ?? 8099);
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: './e2e',
  // Each spec drives one shared server and database, so they must not race.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],
  timeout: 30_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],

  webServer: {
    // scripts/e2e-server.sh builds the SPA, creates a scratch SQLite database,
    // and starts uvicorn against it. The app serves the built SPA itself, so
    // there is no second dev server to keep in sync.
    command: './scripts/e2e-server.sh',
    url: `${BASE_URL}/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    stdout: 'pipe',
    stderr: 'pipe',
    env: {
      E2E_PORT: String(PORT),
    },
  },
});
