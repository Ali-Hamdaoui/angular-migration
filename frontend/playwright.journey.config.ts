import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const edgeExecutable = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "journey-command-center.spec.ts",
  outputDir: path.join(process.cwd(), "test-results", "journey-command-center"),
  reporter: [["list"]],
  workers: 1,
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: process.env.JOURNEY_FRONTEND_URL || "http://127.0.0.1:3000",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    launchOptions: { executablePath: edgeExecutable },
  },
  projects: [{ name: "edge", use: { ...devices["Desktop Edge"] } }],
});
