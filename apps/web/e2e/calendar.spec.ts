import { expect, test } from '@playwright/test';

import { t } from '@/i18n';

import { signIn } from './sign-in';

/**
 * Календарь на живом стеке. Сделок у нового пользователя нет и быть не может: их приносит
 * синк, которого на этой машине нет, — поэтому смоук проверяет не суммы, а то, что от сумм
 * не зависит: экран открывается, месяц живёт в адресе и переживает перезагрузку настоящим
 * браузером, а испорченная ссылка не роняет страницу и не уходит на сервер за месяцем,
 * которого тот не примет.
 *
 * Суммы проверяются на засеянной базе руками (DoD `S2-09`): сумма дня в ячейке против
 * суммы колонки журнала, открытого кликом по этому дню.
 */
test('месяц календаря переживает перезагрузку, испорченная ссылка не роняет экран', async ({
  page,
}) => {
  await signIn(page);

  await page.goto('/calendar');
  await expect(page.getByRole('heading', { name: t.pages.calendar })).toBeVisible();
  // Счетов у нового пользователя нет, и календарь говорит именно это, а не «сделок нет».
  await expect(page.getByText(t.calendar.emptyAccounts)).toBeVisible();

  // Текущий месяц — состояние по умолчанию, и в адресе его нет.
  await expect(page).toHaveURL(/\/calendar$/);

  await page.getByRole('button', { name: t.calendar.prevMonth }).click();
  await expect(page).toHaveURL(/month=\d{4}-\d{2}/);
  const url = new URL(page.url());
  const month = url.searchParams.get('month') ?? '';

  await page.reload();
  await expect(page.getByRole('heading', { name: t.pages.calendar })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`month=${month}`));

  await page.getByRole('button', { name: t.calendar.currentMonth }).click();
  await expect(page).toHaveURL(/\/calendar$/);

  // Чужая ссылка с мусором в параметре: экран обязан открыться на текущем месяце, а не
  // показать ошибку — и не отправить серверу месяц, который тот отвергает как 400.
  await page.goto('/calendar?month=2026-13');
  await expect(page.getByRole('heading', { name: t.pages.calendar })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);

  await page.goto('/calendar?month=%00%00&month=');
  await expect(page.getByRole('heading', { name: t.pages.calendar })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});
