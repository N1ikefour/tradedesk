import { expect, test } from '@playwright/test';

import { t } from '@/i18n';

import { signIn } from './sign-in';

/**
 * Экран счетов на живом стеке: счёт заводится формой, переживает перезагрузку (значит
 * доехал до базы, а не остался состоянием страницы) и удаляется подтверждением по имени.
 *
 * DoD из `SPEC.md` §12 — «через минуту статус `connected` и позиций > 0» — здесь
 * недостижим: сделки приносит коллектор MT5, а он запускается только на Windows, и на
 * стенде смоука его нет. Поэтому смоук доходит до `pending` — состояния, в котором счёт
 * и обязан ждать коллектора.
 */
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

  // `T-07`: пароля счёта форма не спрашивает вовсе, и на живой странице поля такого типа
  // нет ни одного. Вместо него — строка о том, чем коллектор попадёт в счёт.
  await expect(form.getByText(t.accounts.loginHint)).toBeVisible();
  expect(await form.locator('input[type="password"]').count()).toBe(0);

  await form.getByRole('button', { name: t.accounts.create, exact: true }).click();

  await expect(form).toBeHidden();
  await expect(page.getByRole('heading', { name: label })).toBeVisible();
  // exact: обычный getByText ловит подстроку без учёта регистра, а слова «ожидает
  // коллектор» стоят ещё и в тексте блока «Коллектор» ниже.
  await expect(page.getByText(t.accounts.statusPending, { exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByRole('heading', { name: label })).toBeVisible();

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
