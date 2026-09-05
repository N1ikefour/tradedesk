import { expect, test } from '@playwright/test';

import { signIn } from './sign-in';

/**
 * DoD задачи S0-07: человек открывает браузер, запрашивает код, берёт его на странице
 * `/dev/outbox` и входит. Сам путь живёт в `sign-in.ts` — им же начинаются остальные
 * смоуки, и второй копии этих шагов быть не должно.
 */
test('вход по коду из /dev/outbox', async ({ page, context }) => {
  await signIn(page, context);

  await expect(page).toHaveURL(/\/$/);
});
