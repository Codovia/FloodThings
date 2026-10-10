import { defineConfig } from '@playwright/test'
import { tmpdir } from 'node:os'

export default defineConfig({
  testDir: './tests', outputDir: `${tmpdir()}/floodpulse-map-test-results`,
  fullyParallel: false, workers: 1, retries: 0,
  use: { baseURL: 'http://127.0.0.1:14173', browserName: 'chromium', viewport: { width: 1280, height: 1100 } },
  webServer: [
    { command: '../backend/.venv/bin/python -B -m uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port 18040', url: 'http://127.0.0.1:18040/api/health', reuseExistingServer: false, timeout: 15000, env: { ...process.env, SHELTER_PUBLIC_ORIGIN: 'http://127.0.0.1:14173', SHELTER_COOKIE_SECURE: 'false' } },
    { command: 'npm run dev -- --host 127.0.0.1 --port 14173 --strictPort', url: 'http://127.0.0.1:14173', reuseExistingServer: false, timeout: 15000, env: { FLOODPULSE_API_TARGET: 'http://127.0.0.1:18040' } },
  ],
})
