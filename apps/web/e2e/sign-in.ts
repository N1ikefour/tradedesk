import { expect, type BrowserContext, type Page } from '@playwright/test';

import { t } from '@/i18n';

/**
 * Вход по коду из `/dev/outbox` — тот же путь, которым идёт человек. Код читается со
 * страницы писем, а не из API: иначе смоук пройдёт и при сломанной странице.
 *
 * Адрес каждый раз новый: лимит на адрес (3 запроса за 10 минут, SPEC.md 4) иначе
 * упирается на втором прогоне подряд.
 */
const CODE_PATTERN = /\b(\d{6})\b/;

export async function signIn(page: Page, context: BrowserContext): Promise<string> {
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
  return email;
}
