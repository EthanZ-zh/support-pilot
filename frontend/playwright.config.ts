import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, devices } from '@playwright/test'

const frontendDir = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(frontendDir, '..')
const python = process.env.E2E_PYTHON ?? (
  process.platform === 'win32' ? '.\\.venv\\Scripts\\python.exe' : 'python'
)
const databaseUrl = process.env.E2E_DATABASE_URL
  ?? 'postgresql+psycopg://support_pilot:support_pilot@127.0.0.1:54330/support_pilot_test'

export default defineConfig({
  testDir: './e2e',
  timeout: 120_000,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI
    ? [['line'], ['html', { open: 'never' }]]
    : [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:15174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: [
        `${python} -m alembic upgrade head`,
        `${python} scripts/seed.py`,
        `${python} scripts/ingest_knowledge.py --provider deterministic`,
        `${python} -m uvicorn support_pilot.main:app --host 127.0.0.1 --port 18001`,
      ].join(' && '),
      cwd: projectRoot,
      url: 'http://127.0.0.1:18001/api/v1/health/ready',
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        SUPPORT_PILOT_DATABASE_URL: databaseUrl,
        SUPPORT_PILOT_AGENT_PROVIDER: 'deterministic',
        SUPPORT_PILOT_RETRIEVAL_PROVIDER: 'deterministic',
        SUPPORT_PILOT_NOTIFICATION_CHANNEL: 'log',
        SUPPORT_PILOT_JWT_SECRET: process.env.SUPPORT_PILOT_JWT_SECRET
          ?? 'e2e-only-jwt-secret-with-at-least-32-characters',
      } as Record<string, string>,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 15174',
      cwd: frontendDir,
      url: 'http://127.0.0.1:15174',
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        ...process.env,
        VITE_API_PROXY_TARGET: 'http://127.0.0.1:18001',
      } as Record<string, string>,
    },
  ],
})
