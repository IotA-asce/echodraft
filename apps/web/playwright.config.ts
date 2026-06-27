import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const root = path.resolve(__dirname, "../..");

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  use: { baseURL: "http://127.0.0.1:3000", ...devices["Desktop Chrome"] },
  webServer: [
    {
      command: "uv run --package echodraft-api uvicorn echodraft_api.main:app --host 127.0.0.1 --port 8000",
      cwd: root,
      env: {
        ECHODRAFT_DATABASE_URL: "sqlite:///./.tmp/playwright/foundations.db",
        ECHODRAFT_ARTIFACT_ROOT: "./.tmp/playwright/artifacts",
        ECHODRAFT_TTS_SETTINGS_PATH: "./.tmp/playwright/tts-settings.json",
        ECHODRAFT_KOKORO_RUNTIME_ROOT: "./.tmp/playwright/kokoro/managed-onnx-v1"
      },
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: false
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1 --port 3000",
      cwd: __dirname,
      env: { NEXT_PUBLIC_API_URL: "http://127.0.0.1:8000" },
      url: "http://127.0.0.1:3000",
      reuseExistingServer: false
    }
  ]
});
