import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Account } from '@/accounts/api';
import { useAccountSelectionStore } from '@/accounts/selection';
import type { CalendarDay, CalendarMonth } from '@/calendar/api';
import { t } from '@/i18n';
import { errorResponse, installFetchMock, jsonResponse, type RouteTable } from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';

const SESSION = 'GET /api/v1/auth/me';
const ACCOUNTS = 'GET /api/v1/accounts';
const CALENDAR = 'GET /api/v1/journal/calendar';

const FIRST_ACCOUNT = '0199a2b0-0000-7000-8000-0000000000a1';
const SECOND_ACCOUNT = '0199a2b0-0000-7000-8000-0000000000a2';

function account(overrides: Partial<Account> = {}): Account {
  return {
    id: FIRST_ACCOUNT,
    label: 'Скальпинг',
    is_demo: false,
    color: '#2563eb',
    platform: 'mt5',
    broker: null,
    server: 'Broker-Real',
    login: 5_001_234,
    currency: 'USD',
    account_type: null,
    server_utc_offset_minutes: null,
    status: 'connected',
    status_message: null,
    last_sync_at: '2026-09-07T09:00:00Z',
    last_heartbeat_at: '2026-09-07T09:01:00Z',
    collector_id: 'nb-01',
    sort_order: 0,
    created_at: '2026-09-01T10:00:00Z',
    positions_count: 400,
    ...overrides,
  };
}

/**
 * День таким, каким его отдаёт сервер: границы посчитаны им (зона `Asia/Yekaterinburg`,
 * начало дня 0 часов), и клиент их не пересчитывает.
 */
function calendarDay(overrides: Partial<CalendarDay> = {}): CalendarDay {
  return {
    day: '2026-09-07',
    starts_at: '2026-09-06T19:00:00Z',
    ends_at: '2026-09-07T19:00:00Z',
    trades: 3,
    wins: 2,
    losses: 1,
    breakeven: 0,
    net_pnl: '42.00',
    by_account: [],
    ...overrides,
  };
}

function calendar(month: string, days: CalendarDay[]): CalendarMonth {
  return {
    month,
    timezone: TEST_USER.timezone,
    day_boundary_hour: TEST_USER.day_boundary_hour,
    days,
  };
}

type Options = {
  accounts?: Account[];
  /** Дни по месяцам: экран спрашивает ровно тот месяц, который стоит в адресе. */
  byMonth?: Record<string, CalendarDay[]>;
  calendarStatus?: number;
};

function withCalendar(options: Options = {}): {
  routes: RouteTable;
  months: string[];
  accountIds: (string | null)[];
} {
  const months: string[] = [];
  const accountIds: (string | null)[] = [];
  return {
    months,
    accountIds,
    routes: {
      [SESSION]: () => jsonResponse(200, TEST_USER),
      [ACCOUNTS]: () => jsonResponse(200, { items: options.accounts ?? [account()] }),
      [CALENDAR]: ({ url }) => {
        const month = url.searchParams.get('month') ?? '';
        months.push(month);
        accountIds.push(url.searchParams.get('account_ids'));
        if (options.calendarStatus !== undefined) {
          return errorResponse(options.calendarStatus, 'internal_error', 'всё сломалось');
        }
        return jsonResponse(200, calendar(month, options.byMonth?.[month] ?? []));
      },
    },
  };
}

async function openCalendar(entry = '/calendar') {
  const rendered = renderApp([entry]);
  await screen.findByRole('heading', { name: t.pages.calendar, level: 1 });
  return rendered;
}

/** Узкий экран: `matchMedia` в jsdom нет вовсе, поэтому раскладка подменяется явно. */
function pretendPhone() {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

beforeEach(() => {
  window.localStorage.clear();
  useAccountSelectionStore.setState({ mode: 'all', ids: [] });
  // Часы фиксированы: месяц по умолчанию — текущий торговый день пользователя, и без
  // фиксации тест зеленел бы только в сентябре 2026.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date('2026-09-07T09:00:00Z'));
  return () => {
    vi.useRealTimers();
  };
});

describe('календарь: день ведёт в журнал', () => {
  it('открывает журнал границами сервера и только закрытыми', async () => {
    installFetchMock(withCalendar({ byMonth: { '2026-09': [calendarDay()] } }).routes);
    await openCalendar();

    // Границы подставлены как есть: правило торгового дня живёт на сервере, второй его
    // реализации на клиенте нет. `status=closed` — DoD S2-09: без него в списке окажутся
    // ещё и позиции, открытые внутри окна, и сумма разойдётся с днём.
    const link = await screen.findByRole('link', { name: /7 число/ });
    expect(link).toHaveAttribute(
      'href',
      '/journal?from=2026-09-06T19%3A00%3A00Z&to=2026-09-07T19%3A00%3A00Z&status=closed',
    );
  });

  it('день без сделок ссылкой не становится: границ у него нет', async () => {
    installFetchMock(withCalendar({ byMonth: { '2026-09': [calendarDay()] } }).routes);
    await openCalendar();

    await screen.findByRole('link', { name: /7 число/ });
    expect(screen.queryByRole('link', { name: /8 число/ })).not.toBeInTheDocument();
  });
});

describe('календарь: разбивка по счетам', () => {
  const day = calendarDay({
    net_pnl: '42.00',
    trades: 5,
    by_account: [
      { account_id: FIRST_ACCOUNT, net_pnl: '50.00', trades: 3 },
      { account_id: SECOND_ACCOUNT, net_pnl: '-8.00', trades: 2 },
    ],
  });
  const twoAccounts = [
    account(),
    account({ id: SECOND_ACCOUNT, label: 'Свинг', color: '#16a34a' }),
  ];

  it('показывает счета дня с их суммами, и они сходятся с днём', async () => {
    installFetchMock(withCalendar({ accounts: twoAccounts, byMonth: { '2026-09': [day] } }).routes);
    await openCalendar();

    expect(await screen.findByText('Скальпинг')).toBeInTheDocument();
    expect(screen.getByText('Свинг')).toBeInTheDocument();
    expect(screen.getByText('50,00 $')).toBeInTheDocument();
    expect(screen.getByText('-8,00 $')).toBeInTheDocument();
  });

  it('та же разбивка есть в подписи ссылки: наведения у чтения с экрана нет', async () => {
    installFetchMock(withCalendar({ accounts: twoAccounts, byMonth: { '2026-09': [day] } }).routes);
    await openCalendar();

    const link = await screen.findByRole('link', { name: /7 число/ });
    expect(link.getAttribute('aria-label')).toContain('Скальпинг');
    expect(link.getAttribute('aria-label')).toContain('Свинг');
  });

  it('на узком экране разбивка стоит в строке открыто — наводить там нечем', async () => {
    pretendPhone();
    installFetchMock(withCalendar({ accounts: twoAccounts, byMonth: { '2026-09': [day] } }).routes);
    await openCalendar();

    expect(await screen.findByText('Свинг')).toBeInTheDocument();
    // Сетки на телефоне нет: сумма дня в ячейке шириной с палец обрезалась бы.
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('день одного счёта разбивки не получает: она повторила бы сумму дня', async () => {
    installFetchMock(
      withCalendar({
        byMonth: {
          '2026-09': [
            calendarDay({
              by_account: [{ account_id: FIRST_ACCOUNT, net_pnl: '42.00', trades: 3 }],
            }),
          ],
        },
      }).routes,
    );
    await openCalendar();

    await screen.findByRole('link', { name: /7 число/ });
    expect(screen.queryByText(t.calendar.breakdownTitle)).not.toBeInTheDocument();
  });

  it('счёт вне списка назван честно, а не пропущен', async () => {
    // Счёт архивировали или удалили, пока экран был открыт: пропущенная строка сделала бы
    // сумму разбивки не равной сумме дня.
    installFetchMock(withCalendar({ byMonth: { '2026-09': [day] } }).routes);
    await openCalendar();

    expect(await screen.findByText(t.calendar.unknownAccount)).toBeInTheDocument();
  });
});

describe('календарь: итоги', () => {
  const days = [
    calendarDay({ day: '2026-09-01', net_pnl: '10.50', trades: 2, wins: 2, losses: 0 }),
    calendarDay({ day: '2026-09-07', net_pnl: '-2.25', trades: 1, wins: 0, losses: 1 }),
  ];

  it('итог месяца — сумма дней ответа, не сложенная через Number', async () => {
    installFetchMock(withCalendar({ byMonth: { '2026-09': days } }).routes);
    await openCalendar();

    expect(await screen.findByText('8,25 $')).toBeInTheDocument();
    expect(screen.getByText(t.calendar.monthTotal)).toBeInTheDocument();
  });

  it('итог недели стоит справа от её дней', async () => {
    installFetchMock(withCalendar({ byMonth: { '2026-09': days } }).routes);
    await openCalendar();

    await screen.findByText('8,25 $');
    // 1 и 7 сентября — разные недели (1-е вторник, 7-е понедельник), поэтому итоги
    // недель равны суммам своих дней и различимы на экране.
    expect(screen.getByRole('columnheader', { name: t.calendar.weekTotal })).toBeInTheDocument();
    expect(screen.getAllByText('10,50 $')).toHaveLength(2);
  });
});

describe('календарь: месяц в адресе', () => {
  it('месяц из адреса спрашивается у сервера и остаётся в адресе', async () => {
    const { routes, months } = withCalendar({ byMonth: { '2026-02': [] } });
    installFetchMock(routes);
    await openCalendar('/calendar?month=2026-02');

    await waitFor(() => expect(months).toContain('2026-02'));
    expect(months).not.toContain('2026-09');
  });

  it('переключение месяца ведёт состояние через адрес и возвращает к текущему', async () => {
    // Состояние экрана — месяц из адреса, поэтому кнопка «Сегодня» и есть его показание:
    // выключена ровно тогда, когда в адресе текущий месяц. Что адрес действительно
    // меняется и переживает перезагрузку, проверяет смоук настоящим браузером.
    const user = userEvent.setup();
    const { routes, months } = withCalendar({ byMonth: { '2026-09': [calendarDay()] } });
    installFetchMock(routes);
    await openCalendar();

    await screen.findByRole('link', { name: /7 число/ });
    expect(screen.getByRole('button', { name: t.calendar.currentMonth })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: t.calendar.prevMonth }));

    await waitFor(() => expect(months).toContain('2026-08'));
    expect(screen.getByRole('button', { name: t.calendar.currentMonth })).toBeEnabled();

    await user.click(screen.getByRole('button', { name: t.calendar.currentMonth }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: t.calendar.currentMonth })).toBeDisabled(),
    );
    expect(months.at(-1)).toBe('2026-09');
  });

  it('мусор в адресе открывает текущий месяц, а не ошибку', async () => {
    const { routes, months } = withCalendar();
    installFetchMock(routes);
    await openCalendar('/calendar?month=2026-13');

    await waitFor(() => expect(months).toContain('2026-09'));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('за пределами того, что принимает сервер, кнопка выключена', async () => {
    installFetchMock(withCalendar().routes);
    await openCalendar('/calendar?month=2100-12');

    expect(await screen.findByRole('button', { name: t.calendar.nextMonth })).toBeDisabled();
    expect(screen.getByRole('button', { name: t.calendar.prevMonth })).toBeEnabled();
  });
});

describe('календарь: состояния', () => {
  it('месяц без сделок объяснён словами, и сетка остаётся на месте', async () => {
    installFetchMock(withCalendar({ byMonth: { '2026-09': [] } }).routes);
    await openCalendar();

    expect(await screen.findByText(t.calendar.empty)).toBeInTheDocument();
    expect(screen.getByText(t.calendar.emptyHint)).toBeInTheDocument();
    expect(screen.getByRole('table', { name: /сентябрь 2026/i })).toBeInTheDocument();
  });

  it('без счетов календарь говорит именно это, а не «сделок нет»', async () => {
    installFetchMock(withCalendar({ accounts: [] }).routes);
    await openCalendar();

    expect(await screen.findByText(t.calendar.emptyAccounts)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: t.calendar.goToAccounts })).toHaveAttribute(
      'href',
      '/accounts',
    );
  });

  it('серверная ошибка показана человеку и повторяется кнопкой', async () => {
    const user = userEvent.setup();
    const { routes, months } = withCalendar({ calendarStatus: 500 });
    installFetchMock(routes);
    await openCalendar();

    expect(await screen.findByRole('alert')).toHaveTextContent(t.calendar.failed);
    const asked = months.length;
    await user.click(screen.getByRole('button', { name: t.common.retry }));
    await waitFor(() => expect(months.length).toBeGreaterThan(asked));
  });

  it('выбор без единого счёта не спрашивает сервер и объясняет пустоту', async () => {
    const { routes, months } = withCalendar({ accounts: [account({ is_demo: true })] });
    installFetchMock(routes);
    useAccountSelectionStore.setState({ mode: 'all_real', ids: [] });
    await openCalendar();

    expect(await screen.findByText(t.calendar.emptyRealAccounts)).toBeInTheDocument();
    expect(months).toHaveLength(0);
  });
});

describe('календарь: переключатель счетов', () => {
  it('смена выбора перезапрашивает месяц без перезагрузки', async () => {
    const { routes, accountIds } = withCalendar({
      accounts: [account(), account({ id: SECOND_ACCOUNT, label: 'Свинг' })],
      byMonth: { '2026-09': [calendarDay()] },
    });
    installFetchMock(routes);
    await openCalendar();

    await screen.findByRole('link', { name: /7 число/ });
    expect(accountIds).toEqual([null]);

    useAccountSelectionStore.setState({ mode: 'single', ids: [SECOND_ACCOUNT] });

    await waitFor(() => expect(accountIds).toContain(SECOND_ACCOUNT));
  });
});
