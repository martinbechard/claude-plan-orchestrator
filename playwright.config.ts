// playwright.config.ts
// Playwright configuration for the pipeline dashboard E2E tests
// Design: docs/plans/2026-03-27-54-validator-should-run-e2e-tests-for-ui-criteria-design.md

import { defineConfig, devices } from '@playwright/test';

const BASE_URL = 'http://localhost:7070';
const E2E_RESULTS_DIR = 'logs/e2e';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [
    ['json', { outputFile: `${E2E_RESULTS_DIR}/results.json` }],
    ['html', { outputFolder: `${E2E_RESULTS_DIR}/html-report`, open: 'never' }],
    ['list'],
  ],
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
