import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against a live stack (web + API + PostgreSQL + Mailpit). See docs/TESTING.md.
 * They never start servers themselves so the same suite can target local, Docker Compose or staging.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  // channel "chromium" runs the full Chromium build in new headless mode (no separate headless-shell download).
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], channel: "chromium" } }],
});
