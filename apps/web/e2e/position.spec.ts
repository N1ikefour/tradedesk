import { expect, test } from '@playwright/test';

import { t } from '@/i18n';

import { signIn } from './sign-in';

/**
 * Карточка позиции на живом стеке. Заполнение рефлексии из SPEC.md 13 смоук пока не
 * покрывает, и причина не в лени: позиций у нового пользователя нет и взяться им неоткуда
 * — их собирает `S1-03` из сделок, которых не приносит никто, а сеялки нет (`X-37`).
 * Открыть нечего, значит и заполнять нечего.
 *
 * Что проверяется без данных: карточка по чужой ссылке отвечает «позиции нет», а не белым
 * экраном, и из неё есть дорога назад в журнал с сохранённым фильтром. Это ровно тот путь,
 * которым в карточку попадают из мессенджера, — и единственный, который сегодня достижим.
 */
const OTHER_POSITION = '0199a2b0-0000-7000-8000-0000000000ff';

test('карточка по чужой ссылке объясняет отсутствие позиции и не роняет экран', async ({
  page,
  context,
}) => {
  await signIn(page, context);

  await page.goto(`/journal/${OTHER_POSITION}?symbol=EURUSD`);

  const card = page.getByRole('dialog');
  await expect(card.getByText(t.errors.positionNotFound)).toBeVisible();
  // Повторять нечего: позиция не появится оттого, что запрос повторили.
  await expect(card.getByRole('button', { name: t.common.retry })).toHaveCount(0);

  await card.getByRole('link', { name: t.position.backToJournal }).click();

  await expect(page).toHaveURL(/\/journal\?symbol=EURUSD/);
  await expect(page.getByRole('heading', { name: t.pages.journal })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
