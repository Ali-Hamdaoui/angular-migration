import { defineConfig, devices } from "@playwright/test";
import os from "node:os";
import path from "node:path";

const temp = path.join(os.tmpdir(), "amfa-r6-playwright");
process.env.NEXT_PUBLIC_BACKEND_URL = "http://127.0.0.1:8000";
const chromium = process.env.LOCALAPPDATA ? path.join(process.env.LOCALAPPDATA, "ms-playwright", "chromium-1234", "chrome-win64", "chrome.exe") : undefined;

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: path.join(temp, "test-results"),
  reporter: [["list"]],
  workers: 1,
  retries: 0,
  fullyParallel: false,
  use: { baseURL: "http://127.0.0.1:3312", headless: true, trace: "retain-on-failure", screenshot: "only-on-failure", video: "off", ...(chromium ? { launchOptions: { executablePath: chromium } } : {}) },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    { command: "set PYTHONPATH=backend&& python -m uvicorn tests.browser_harness.r6_app:app --host 127.0.0.1 --port 8000", cwd: "..", url: "http://127.0.0.1:8000/__test__/r6/metrics", reuseExistingServer: true, timeout: 120_000 },
    { command: "npm run dev -- --hostname 127.0.0.1 --port 3312", cwd: ".", url: "http://127.0.0.1:3312", reuseExistingServer: true, timeout: 120_000 },
  ],
});
