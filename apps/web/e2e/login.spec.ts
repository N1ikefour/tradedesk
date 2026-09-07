import { expect, test } from '@playwright/test';

import { t } from '@/i18n';

import { signIn } from './sign-in';

/**
 * DoD задачи S0-07: человек открывает браузер, запрашивает код, берёт его на странице
 * `/dev/outbox` и входит. Сам путь живёт в `sign-in.ts` — им же начинаются остальные
 * смоуки, и второй копии этих шагов быть не должно.
 *
 * Сюда же добавлена проверка того, **куда** вход приводит (`S2-10`): у нового
 * пользователя нет ни счетов, ни позиций, и первый экран обязан объяснять, что делать
 * дальше, а не выглядеть поломкой. Отдельным смоуком это не сделать: каждый файл входит
 * заново, а код входа ограничен десятью запросами в час на IP (SPEC.md 4), и шестая
 * точка входа сделала бы `make smoke` неповторяемым.
 */
test('вход по коду из /dev/outbox приводит на дашборд с шагами онбординга', async ({
  page,
  context,
}) => {
  await signIn(page, context);

  await expect(page).toHaveURL(/\/$/);

  await expect(page.getByText(t.dashboard.stepAccountTitle)).toBeVisible();
  await expect(page.getByText(t.dashboard.stepReflectionTitle)).toBeVisible();
  // Ни один шаг не отмечен: галочки считаются по факту, а не по времени.
  await expect(page.getByText(t.dashboard.onboardingDone, { exact: true })).toHaveCount(0);
  // Пустых рамок с прочерками нет — их читают как «не загрузилось».
  await expect(page.getByText(t.dashboard.summaryTitle)).toHaveCount(0);
  await expect(page.getByText(t.dashboard.openTitle)).toHaveCount(0);
  await expect(page.getByText(t.dashboard.attentionEmpty)).toBeVisible();

  await page.getByRole('link', { name: t.dashboard.stepAccountAction }).click();
  await expect(page).toHaveURL(/\/accounts$/);
});
