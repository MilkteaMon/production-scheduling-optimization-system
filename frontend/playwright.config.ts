import { defineConfig, devices } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
const root = resolve(import.meta.dirname, "..");
const testFolder = resolve(root, "runtime", "browser-tests");
mkdirSync(testFolder, { recursive: true });
const testUrl = process.env.OPSPILOT_BASE_URL ?? "http://127.0.0.1:8011";
const python = resolve(
  root,
  "backend",
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
export default defineConfig({
  testDir: "./tests",
  timeout: 120000,
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  webServer: process.env.OPSPILOT_BASE_URL
    ? undefined
    : {
        command: `"${python}" -m uvicorn opspilot.api.main:app --host 127.0.0.1 --port 8011`,
        cwd: root,
        url: `${testUrl}/api/v1/health`,
        reuseExistingServer: false,
        timeout: 60000,
        env: {
          DATABASE_URL: `sqlite:///${resolve(testFolder, `browser-${process.pid}.db`).replaceAll("\\", "/")}`,
          AI_ENABLED: "false",
          AI_PROVIDER: "openai_api",
          OPENAI_API_KEY: "",
        },
      },
  use: {
    baseURL: testUrl,
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], channel: process.env.CI ? undefined : "chrome" },
    },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"], channel: process.env.CI ? undefined : "chrome" },
    },
  ],
});
