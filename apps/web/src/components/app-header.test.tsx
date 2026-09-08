/**
 * Меню шапки на узком экране (X-36) и общий слой закрытия (`lib/use-dismiss`).
 *
 * Раскладку эти тесты не проверяют: `md:hidden` и `hidden md:flex` — правила CSS, а в
 * jsdom стилей нет, поэтому обе навигации живут в документе одновременно. Меню поэтому и
 * ищется через `aria-controls`, а не по имени — соседний `nav` называется так же.
 * Ширину, на которой меню сменяет строку, проверяет смоук в браузере (`e2e/login.spec`).
 *
 * Всё остальное от ширины не зависит и проверяется здесь: на телефоне это меню — вся
 * навигация приложения, и «не открылось» означает «пользоваться нечем».
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { Account } from '@/accounts/api';
import { t } from '@/i18n';
import { installFetchMock, jsonResponse, type RouteTable } from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';

const SESSION = 'GET /api/v1/auth/me';
const ACCOUNTS = 'GET /api/v1/accounts';

const FIRST_ACCOUNT = '0199a2b0-0000-7000-8000-0000000000a1';
const SECOND_ACCOUNT = '0199a2b0-0000-7000-8000-0000000000a2';

function account(overrides: Partial<Account> = {}): Account {
  return {
    id: FIRST_ACCOUNT,
    label: 'Демо A',
    is_demo: true,
    color: '#2563eb',
    platform: 'mt5',
    broker: null,
    server: 'Broker-Demo',
    login: 5_001_234,
    currency: 'USD',
    account_type: null,
    server_utc_offset_minutes: null,
    status: 'connected',
    status_message: null,
    last_sync_at: null,
    last_heartbeat_at: null,
    collector_id: null,
    sort_order: 0,
    created_at: '2026-09-01T10:00:00Z',
    positions_count: 0,
    ...overrides,
  };
}

function withAccounts(items: Account[] = [account()]): RouteTable {
  return {
    [SESSION]: () => jsonResponse(200, TEST_USER),
    [ACCOUNTS]: () => jsonResponse(200, { items }),
  };
}

function menuTrigger(): HTMLElement {
  return screen.getByRole('button', { name: t.header.openMenu });
}

/** Открытый список меню — тот, на который показывает `aria-controls` кнопки. */
function openedMenu(): HTMLElement {
  const id = menuTrigger().getAttribute('aria-controls');
  if (id === null) {
    throw new Error('Меню закрыто: у кнопки нет aria-controls');
  }
  const list = document.getElementById(id);
  if (list === null) {
    throw new Error(`Списка меню ${id} нет в документе`);
  }
  return list;
}

/** Календарь — самый дешёвый экран под шапкой: заглушка без единого запроса. */
async function openCalendarWithMenu(
  user: ReturnType<typeof userEvent.setup>,
): Promise<HTMLElement> {
  renderApp(['/calendar']);
  await screen.findByRole('heading', { name: t.pages.calendar });
  await user.click(menuTrigger());
  return openedMenu();
}

describe('Меню шапки', () => {
  it('кнопка открывает и закрывает список, aria-expanded следует за состоянием', async () => {
    installFetchMock(withAccounts());
    const user = userEvent.setup();

    renderApp(['/calendar']);
    await screen.findByRole('heading', { name: t.pages.calendar });
    expect(menuTrigger()).toHaveAttribute('aria-expanded', 'false');

    await user.click(menuTrigger());
    const menu = openedMenu();
    expect(menuTrigger()).toHaveAttribute('aria-expanded', 'true');

    await user.click(menuTrigger());
    expect(menuTrigger()).toHaveAttribute('aria-expanded', 'false');
    expect(menu).not.toBeInTheDocument();
  });

  it('в меню те же разделы, что в строке навигации: на телефоне другой нет', async () => {
    installFetchMock(withAccounts());
    const user = userEvent.setup();

    const menu = await openCalendarWithMenu(user);
    const row = screen
      .getAllByRole('navigation', { name: t.header.menu })
      .find((nav) => nav !== menu);
    if (row === undefined) {
      throw new Error('Строки навигации нет в документе');
    }

    const labels = within(menu)
      .getAllByRole('link')
      .map((link) => link.textContent);
    expect(labels).toEqual(
      within(row)
        .getAllByRole('link')
        .map((link) => link.textContent),
    );
    // «Настройки» — первый пункт, который уезжает за край строки (на 768px виден меньше
    // чем наполовину); в меню он обязан быть целиком.
    expect(labels).toContain(t.nav.settings);
  });

  it('Escape закрывает меню и возвращает фокус на кнопку', async () => {
    installFetchMock(withAccounts());
    const user = userEvent.setup();

    const menu = await openCalendarWithMenu(user);
    await user.tab();
    expect(within(menu).getAllByRole('link')[0]).toHaveFocus();

    await user.keyboard('{Escape}');

    expect(menu).not.toBeInTheDocument();
    // Иначе фокус достаётся `body`, и следующий Tab уводит в начало страницы.
    expect(menuTrigger()).toHaveFocus();
  });

  it('клик мимо закрывает меню', async () => {
    installFetchMock(withAccounts());
    const user = userEvent.setup();

    const menu = await openCalendarWithMenu(user);
    await user.click(screen.getByRole('heading', { name: t.pages.calendar }));

    expect(menu).not.toBeInTheDocument();
    expect(menuTrigger()).toHaveAttribute('aria-expanded', 'false');
  });

  it('переход по пункту открывает раздел и закрывает меню за собой', async () => {
    installFetchMock(withAccounts());
    const user = userEvent.setup();

    const menu = await openCalendarWithMenu(user);
    await user.click(within(menu).getByRole('link', { name: t.nav.accounts }));

    expect(await screen.findByRole('heading', { name: t.pages.accounts })).toBeInTheDocument();
    // Открытое меню поверх нового экрана закрывало бы его целиком.
    expect(menu).not.toBeInTheDocument();
    expect(menuTrigger()).toHaveAttribute('aria-expanded', 'false');
  });

  it('меню открывается с клавиатуры', async () => {
    installFetchMock(withAccounts());
    const user = userEvent.setup();

    renderApp(['/calendar']);
    await screen.findByRole('heading', { name: t.pages.calendar });

    menuTrigger().focus();
    await user.keyboard('{Enter}');

    expect(openedMenu()).toBeInTheDocument();
  });

  it('Escape в переключателе счетов тоже возвращает фокус на его кнопку', async () => {
    // Два счёта: при одном переключатель — надпись без списка (SPEC.md 9.2).
    installFetchMock(withAccounts([account(), account({ id: SECOND_ACCOUNT, label: 'Реал Б' })]));
    const user = userEvent.setup();

    renderApp(['/calendar']);
    await screen.findByRole('heading', { name: t.pages.calendar });

    const trigger = await screen.findByRole('button', { name: t.accountSwitcher.open });
    await user.click(trigger);
    // Фокус уводится в список: оставшись на кнопке, он «вернулся» бы туда и без починки.
    await user.tab();
    expect(screen.getByRole('button', { name: t.accountSwitcher.all })).toHaveFocus();

    await user.keyboard('{Escape}');

    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(trigger).toHaveFocus();
  });
});
