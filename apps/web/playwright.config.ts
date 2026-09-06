import { defineConfig, devices } from '@playwright/test';

/**
 * Смоук входа (SPEC.md 13). Гоняется целью `make smoke` против поднятого
 * `docker compose --profile local` — сервер здесь не поднимается намеренно:
 * смоук проверяет ту же установку, которую человек открывает браузером.
 *
 * В `make ci` не входит: браузеры ставятся отдельной командой и весят сотни мегабайт.
 * Из набора SPEC.md 13 достижимы вход, счета и журнал; ручная сделка, рефлексия и
 * календарь появятся вместе со своими экранами.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  // Повторов нет: лимит по IP (10 запросов кода в час, SPEC.md 4) делает вторую
  // попытку не такой же, а хуже первой — ретрай прятал бы настоящую причину.
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.SMOKE_BASE_URL ?? 'http://localhost:5173',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: devices['Desktop Chrome'] }],
});
