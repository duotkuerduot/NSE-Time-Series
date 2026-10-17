// Browser tests (ENGINEERING.md §16.4, §16.5).
//   pnpm e2e                         smoke and axe checks against the contract fixtures
//   NSEFC_E2E_URL=http://127.0.0.1:8765 pnpm e2e
//                                    end to end against `nsefc serve` after `nsefc run --sample`
import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;
const external = process.env.NSEFC_E2E_URL;
// A preinstalled Chromium can stand in for Playwright's own download.
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined;

export default defineConfig({
  testDir: "e2e",
  testMatch: external ? "sample.spec.ts" : "smoke.spec.ts",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: {
    baseURL: external ?? `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    launchOptions: { executablePath },
  },
  projects: [
    { name: "mobile", use: { ...devices["Pixel 7"], launchOptions: { executablePath } } },
    { name: "desktop", use: { ...devices["Desktop Chrome"], launchOptions: { executablePath } } },
  ],
  webServer: external
    ? undefined
    : {
        // The preview server serves the production build plus the fixture API (vite.config.ts).
        command: `pnpm exec vite build && pnpm exec vite preview --host 127.0.0.1 --port ${PORT} --strictPort`,
        url: `http://127.0.0.1:${PORT}`,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
});
