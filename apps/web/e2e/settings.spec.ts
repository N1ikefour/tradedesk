import { expect, test } from '@playwright/test';

import { t } from '@/i18n';

import { signIn } from './sign-in';

/**
 * DoD задачи S0-08: выбранная таймзона меняет отображение времени и переживает
 * перезагрузку. Проверяется на живом стеке: настройки едут в базу через PATCH, а не
 * остаются состоянием страницы.
 */
/**
 * `Asia/Kolkata` выбран не случайно: браузер это имя не предлагает вовсе (ICU считает
 * каноническим `Asia/Calcutta`), а сервер принимает только его. Пока меню строилось из
 * `Intl`, единственный индийский пункт сохранить было нельзя — 400 без выхода. Смоук
 * проходит этот путь целиком, до записи в базу.
 */
const TARGET_TIME_ZONE = 'Asia/Kolkata';
const OTHER_TIME_ZONE = 'America/New_York';
const TARGET_HOUR = '9';

/** Подпись примера без значения — по ней находится строка с часами. */
const PREVIEW_PREFIX = t.settings.previewNow('');
const DATE_TIME = /\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}$/;

test('таймзона и начало дня сохраняются и переживают перезагрузку', async ({ page }) => {
  await signIn(page);

  await page.goto('/settings');
  const timezone = page.getByLabel(t.settings.timezoneLabel, { exact: true });
  const dayBoundary = page.getByLabel(t.settings.dayBoundaryLabel, { exact: true });
  const preview = page.getByText(PREVIEW_PREFIX);

  await expect(timezone).toBeVisible();
  const initial = await preview.innerText();

  // Зона профиля по умолчанию неизвестна: берём заведомо другую, чтобы время сдвинулось.
  const current = await timezone.inputValue();
  const target = current === TARGET_TIME_ZONE ? OTHER_TIME_ZONE : TARGET_TIME_ZONE;
  await timezone.selectOption(target);

  // Пример меняется до сохранения — иначе человек выбирает зону вслепую.
  await expect(preview).not.toHaveText(initial);

  await dayBoundary.selectOption(TARGET_HOUR);
  await page.getByRole('button', { name: t.settings.save }).click();
  await expect(page.getByText(t.settings.saved)).toBeVisible();

  await page.reload();

  await expect(timezone).toHaveValue(target);
  await expect(dayBoundary).toHaveValue(TARGET_HOUR);
  await expect(preview).toHaveText(DATE_TIME);
});
