import { expect, test } from '@playwright/test';

import { t } from '@/i18n';

import { signIn } from './sign-in';

/**
 * Журнал на живом стеке. Позиций у нового пользователя нет и быть не может: их собирает
 * `S1-03` из сделок, которых не приносит никто, — поэтому смоук проверяет не строки, а
 * то, что от строк не зависит: экран открывается, фильтр переживает перезагрузку
 * настоящим браузером, а испорченная ссылка не роняет страницу.
 */
test('фильтр журнала переживает перезагрузку, испорченная ссылка не роняет экран', async ({
  page,
}) => {
  await signIn(page);

  await page.goto('/journal');
  await expect(page.getByRole('heading', { name: t.pages.journal })).toBeVisible();
  // Счетов у нового пользователя нет, и журнал говорит именно это, а не «сделок нет».
  await expect(page.getByText(t.journal.emptyAccounts)).toBeVisible();

  const symbol = page.getByLabel(t.journal.symbolLabel, { exact: true });
  await symbol.fill('XAUUSD');
  await page.getByRole('button', { name: t.journal.apply, exact: true }).click();
  await page.getByRole('button', { name: t.journal.periodWeek, exact: true }).click();

  await expect(page).toHaveURL(/symbol=XAUUSD/);
  await expect(page).toHaveURL(/period=week/);

  await page.reload();

  await expect(page.getByLabel(t.journal.symbolLabel, { exact: true })).toHaveValue('XAUUSD');
  await expect(
    page.getByRole('button', { name: t.journal.periodWeek, exact: true }),
  ).toHaveAttribute('aria-pressed', 'true');

  // Чужая ссылка с мусором в параметрах: экран обязан открыться, а не показать ошибку.
  await page.goto('/journal?direction=diagonal&sort=DROP%20TABLE&result=nope&period=никогда');
  await expect(page.getByRole('heading', { name: t.pages.journal })).toBeVisible();
  await expect(page.getByLabel(t.journal.directionLabel, { exact: true })).toHaveValue('');

  // Управляющие символы в адресе. Проверяется против настоящего API: `\x00` не снимается
  // `trim()` и валит запрос в 500 на стороне Postgres — то есть присланная ссылка роняла
  // бы журнал получателю. Экран обязан открыться, а не показать ошибку загрузки.
  await page.goto('/journal?symbol=%00%00EURUSD&q=%00abc&tags=%00tag&from=99999-01-01');
  await expect(page.getByRole('heading', { name: t.pages.journal })).toBeVisible();
  await expect(page.getByText(t.journal.emptyAccounts)).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});
