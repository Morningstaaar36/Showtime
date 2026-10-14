import { defineConfig } from "@playwright/test";

// Journeys run against the running app (make up or make dev). One worker keeps memory low.
export default defineConfig({
  testDir: "e2e",
  testMatch: /.*\.spec\.ts/,
  workers: 1,
  timeout: 180_000,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.BASE ?? "http://127.0.0.1:5173",
    viewport: { width: 1600, height: 900 },
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist"] },
    trace: "retain-on-failure",
  },
});
