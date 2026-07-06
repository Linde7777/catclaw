import { defineConfig } from '@playwright/test'

const port = Number(process.env.BIONIC_BOT_E2E_PORT ?? '5173')
const backendPort = Number(process.env.BIONIC_BOT_E2E_BACKEND_PORT ?? String(18_000 + (process.pid % 1000)))
const baseRoot = `/tmp/bionic-bot-e2e-${process.pid}`
const memoriesRoot = `${baseRoot}/memories`
const modelConfig = process.env.BIONIC_BOT_MODEL_CONFIG ?? 'openai-codex'

// 注意：Playwright 的 webServer 在主进程启动；测试代码通常跑在 worker 子进程里，process.pid 不一致。
// 这里把实际使用的 baseRoot 通过环境变量传给 worker，方便在测试结束时打印/排查。
process.env.BIONIC_BOT_E2E_BASE_ROOT = baseRoot

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: 'retain-on-failure',
  },
  webServer: {
    command:
      `cd .. && rm -rf ${baseRoot} && mkdir -p ${baseRoot} && BIONIC_BOT_E2E_PORT=${port} BIONIC_BOT_PORT=${backendPort} BIONIC_BOT_BACKEND_ORIGIN=http://127.0.0.1:${backendPort} BIONIC_BOT_ROOT=${baseRoot} BIONIC_BOT_MODEL_CONFIG=${modelConfig} BIONIC_BOT_MEMORIES_ROOT=${memoriesRoot} ./dev.sh`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
