import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    launchOptions:
      process.env.PLAYWRIGHT_CHROMIUM_PATH != null
        ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH }
        : {},
  },
  reporter: [["list"]],
});
