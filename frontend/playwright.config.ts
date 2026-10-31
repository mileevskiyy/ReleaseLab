import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 90000,
  use: {
    actionTimeout: 10000,
    baseURL: process.env.DEMO_URL || "http://127.0.0.1:3800",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: process.env.DEMO_URL
    ? undefined
    : {
        command:
          "../.venv/bin/uvicorn backend.app:create_app --factory --app-dir .. --host 127.0.0.1 --port 3800",
        url: "http://127.0.0.1:3800/api/health",
        reuseExistingServer: false,
        timeout: 30000,
      },
  reporter: "list",
});
