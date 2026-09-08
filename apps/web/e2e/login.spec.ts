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
 * дальше, а не выглядеть поломкой. И меню шапки на узком экране (`X-36`) — по той же
 * причине: отдельным смоуком это не сделать, каждый файл входит заново, а код входа
 * ограничен десятью запросами в час на IP (SPEC.md 4), и шестая точка входа сделала бы
 * `make smoke` неповторяемым.
 */
test('вход по коду из /dev/outbox приводит на дашборд с шагами онбординга', async ({ page }) => {
  await signIn(page);

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

  // Единственное в меню шапки, чего не проверить в jsdom: `md:hidden` и `hidden md:flex` —
  // правила CSS, а стилей там нет, и обе навигации живут в документе одновременно
  // (`src/components/app-header.test.tsx`). Поведение меню проверено там, здесь — только
  // то, что на телефоне видно его, а не обрубок строки навигации.
  const menuButton = page.getByRole('button', { name: t.header.openMenu });
  const visibleNav = page.locator('header nav:visible');

  await page.setViewportSize({ width: 375, height: 812 });
  await expect(menuButton).toBeVisible();
  await expect(visibleNav).toHaveCount(0);

  await menuButton.click();
  await visibleNav.getByRole('link', { name: t.nav.settings }).click();
  await expect(page).toHaveURL(/\/settings$/);

  // На широком экране всё наоборот: разделы в строку, кнопки нет.
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(menuButton).toBeHidden();
  await expect(visibleNav.getByRole('link', { name: t.nav.settings })).toBeVisible();
});
