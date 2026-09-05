import { expect, test } from '@playwright/test';

import { t } from '@/i18n';

/**
 * DoD задачи S0-07: человек открывает браузер, запрашивает код, берёт его на странице
 * `/dev/outbox` и входит. Код читается со страницы, а не из API: иначе смоук пройдёт
 * и при сломанной странице писем, которой человек как раз и пользуется.
 *
 * Адрес каждый раз новый — лимит на адрес (3 запроса за 10 минут, SPEC.md 4) иначе
 * упирается на втором прогоне подряд.
 */
const CODE_PATTERN = /\b(\d{6})\b/;

test('вход по коду из /dev/outbox', async ({ page, context }) => {
  const email = `smoke-${Date.now()}@example.com`;

  await page.goto('/login');
  await page.getByLabel(t.login.emailLabel).fill(email);
  await page.getByRole('button', { name: t.login.requestCode }).click();

  const codeField = page.getByLabel(t.login.codeLabel);
  await expect(codeField).toBeVisible();

  const outbox = await context.newPage();
  await outbox.goto('/dev/outbox');
  const letter = outbox.locator('li', { hasText: email }).first();
  await expect(letter).toBeVisible();
  const body = (await letter.locator('pre').innerText()).trim();
  await outbox.close();

  const code = CODE_PATTERN.exec(body)?.[1];
  expect(code, `в письме нет шестизначного кода: ${body}`).toBeTruthy();

  // Шестая цифра отправляет форму сама (SPEC.md 9.3) — кнопку жать не нужно.
  await codeField.fill(code as string);

  await expect(page.getByRole('heading', { name: t.pages.dashboard })).toBeVisible();
  await expect(page).toHaveURL(/\/$/);
});
