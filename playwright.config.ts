import { defineConfig } from "@playwright/test";

/**
 * End-to-end check of the Phase 1 flow against running dev servers:
 *   API on :8000 (uvicorn) and web on :3000 (next dev), with the homebrew
 *   test ROM from scripts/make-test-rom.py in data/roms/gba/.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
      : undefined,
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
