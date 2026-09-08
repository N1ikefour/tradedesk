import { expect, test, type Page } from '@playwright/test';

import { t } from '@/i18n';

import { signIn } from './sign-in';

/**
 * Экран счетов на живом стеке: счёт заводится формой, переживает перезагрузку (значит
 * доехал до базы, а не остался состоянием страницы) и удаляется подтверждением по имени.
 *
 * DoD из `SPEC.md` §12 — «через минуту статус `connected` и позиций > 0» — здесь
 * недостижим: сделки приносит коллектор MT5, а его ещё нет (`S1-10`), и запускается он
 * только на Windows. Поэтому смоук доходит до `pending` — состояния, в котором счёт и
 * обязан ждать коллектора.
 */
const INVESTOR_PASSWORD = 'smoke-investor-8f21';

/**
 * Где пароль может остаться на живой странице. Разметки мало: значение поля живёт в
 * свойстве `value`, и проверка одного `page.content()` прошла бы над заполненным полем.
 */
async function passwordTraces(page: Page, secret: string) {
  return page.evaluate((value) => {
    const fields = document.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>(
      'input, textarea',
    );
    return {
      markup: document.documentElement.outerHTML.includes(value),
      fields: Array.from(fields).filter((field) => field.value.includes(value)).length,
    };
  }, secret);
}

test('счёт добавляется, переживает перезагрузку и удаляется вводом имени', async ({ page }) => {
  await signIn(page);

  const label = `Smoke ${Date.now()}`;

  await page.goto('/accounts');
  await expect(page.getByText(t.accounts.empty)).toBeVisible();

  await page.getByRole('button', { name: t.accounts.add }).click();
  const form = page.getByRole('dialog');
  await form.getByLabel(t.accounts.labelLabel, { exact: true }).fill(label);
  await form.getByLabel(t.accounts.serverLabel, { exact: true }).fill('Smoke-Server');
  await form.getByLabel(t.accounts.loginLabel, { exact: true }).fill('5001234');

  // Подсказка про инвесторский пароль — главное содержимое этой формы: человек вводит
  // пароль от счёта с деньгами, и объяснение обязано быть на экране, а не в документации.
  await expect(form.getByText(t.accounts.passwordWhy)).toBeVisible();
  await form.getByLabel(t.accounts.passwordLabel, { exact: true }).fill(INVESTOR_PASSWORD);

  await form.getByRole('button', { name: t.accounts.create, exact: true }).click();

  await expect(form).toBeHidden();
  await expect(page.getByRole('heading', { name: label })).toBeVisible();
  // exact: обычный getByText ловит подстроку без учёта регистра, а слова «ожидает
  // коллектор» стоят ещё и в тексте блока «Коллектор» ниже.
  await expect(page.getByText(t.accounts.statusPending, { exact: true })).toBeVisible();

  // Пароль не возвращается ни в ответе, ни в разметке, ни в полях — проверяется фактом
  // на живой странице.
  expect(await passwordTraces(page, INVESTOR_PASSWORD)).toEqual({ markup: false, fields: 0 });

  await page.reload();
  await expect(page.getByRole('heading', { name: label })).toBeVisible();
  expect(await passwordTraces(page, INVESTOR_PASSWORD)).toEqual({ markup: false, fields: 0 });

  await page.getByRole('button', { name: t.accounts.delete, exact: true }).click();
  const confirm = page.getByRole('dialog');
  await expect(confirm.getByText(t.accounts.deleteLead)).toBeVisible();

  // Чужое имя не удаляет ничего: подтверждение обязано быть точным.
  await confirm.getByRole('textbox').fill('не то имя');
  await confirm.getByRole('button', { name: t.accounts.deleteConfirm, exact: true }).click();
  await expect(confirm.getByText(t.accounts.deleteConfirmMismatch)).toBeVisible();

  await confirm.getByRole('textbox').fill(label);
  await confirm.getByRole('button', { name: t.accounts.deleteConfirm, exact: true }).click();

  await expect(confirm).toBeHidden();
  await expect(page.getByText(t.accounts.empty)).toBeVisible();
});
