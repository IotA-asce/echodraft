import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const root = path.resolve(__dirname, "../..");
const apiPort = process.env.ECHODRAFT_E2E_API_PORT ?? "8000";
const webPort = process.env.ECHODRAFT_E2E_WEB_PORT ?? "3000";
const apiUrl = `http://127.0.0.1:${apiPort}`;
const webUrl = `http://127.0.0.1:${webPort}`;

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  use: { baseURL: webUrl, ...devices["Desktop Chrome"] },
  webServer: [
    {
      command: `uv run --package echodraft-api uvicorn echodraft_api.main:app --host 127.0.0.1 --port ${apiPort}`,
      cwd: root,
      env: {
        ECHODRAFT_DATABASE_URL: "sqlite:///./.tmp/playwright/foundations.db",
        ECHODRAFT_ARTIFACT_ROOT: "./.tmp/playwright/artifacts",
        ECHODRAFT_TTS_SETTINGS_PATH: "./.tmp/playwright/tts-settings.json",
        ECHODRAFT_KOKORO_RUNTIME_ROOT: "./.tmp/playwright/kokoro/managed-onnx-v1"
      },
      url: `${apiUrl}/health`,
      reuseExistingServer: false
    },
    {
      command: `npm run dev -- --hostname 127.0.0.1 --port ${webPort}`,
      cwd: __dirname,
      env: { NEXT_PUBLIC_API_URL: apiUrl },
      url: webUrl,
      reuseExistingServer: false
    }
  ]
});
