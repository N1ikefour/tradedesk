import { act, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Account } from '@/accounts/api';
import { useAccountSelectionStore } from '@/accounts/selection';
import type { CalendarDay, CalendarMonth, Summary } from '@/dashboard/api';
import { OPEN_POSITIONS_LIMIT, UNREFLECTED_PROBE_LIMIT } from '@/dashboard/api';
import { t } from '@/i18n';
import type { PositionListItem } from '@/journal/api';
import { errorResponse, installFetchMock, jsonResponse, type RouteTable } from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';

const SESSION = 'GET /api/v1/auth/me';
const ACCOUNTS = 'GET /api/v1/accounts';
const POSITIONS = 'GET /api/v1/journal/positions';
const SUMMARY = 'GET /api/v1/analytics/summary';
const CALENDAR = 'GET /api/v1/journal/calendar';

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
    last_sync_at: '2026-09-07T09:00:00Z',
    last_heartbeat_at: '2026-09-07T09:01:00Z',
    collector_id: 'nb-01',
    sort_order: 0,
    created_at: '2026-09-01T10:00:00Z',
    positions_count: 400,
    ...overrides,
  };
}

/** Сводка примера `docs/metrics.md` §4 — восемь закрытых позиций и две открытые. */
function summary(overrides: Partial<Summary> = {}): Summary {
  return {
    trades: 8,
    wins: 4,
    losses: 3,
    breakeven: 1,
    open_positions: 2,
    winrate: '0.5000',
    net_pnl: '117.00',
    gross_pnl: '144.50',
    commission: '-22.00',
    swap: '-4.50',
    fee: '-1.00',
    profit_factor: '2.17',
    avg_win: '54.25',
    avg_loss: '-33.33',
    expectancy: '14.63',
    best_trade: '116.00',
    worst_trade: '-52.00',
    ...overrides,
  };
}

function calendarDay(overrides: Partial<CalendarDay> = {}): CalendarDay {
  return {
    day: '2026-09-07',
    // Границы дня считает сервер: зона пользователя UTC+5, начало дня — 0 часов.
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

function calendar(days: CalendarDay[]): CalendarMonth {
  return {
    month: '2026-09',
    timezone: TEST_USER.timezone,
    day_boundary_hour: TEST_USER.day_boundary_hour,
    days,
  };
}

function position(index: number, overrides: Partial<PositionListItem> = {}): PositionListItem {
  return {
    id: `0199a2b0-0000-7000-8000-${String(index).padStart(12, '0')}`,
    position_id: 100_000 + index,
    symbol_raw: 'EURUSD.m',
    symbol_norm: 'EURUSD',
    direction: 'long',
    status: 'open',
    result: null,
    open_time: '2026-09-07T08:00:00Z',
    close_time: null,
    volume_opened: '0.50000000',
    volume_closed: '0.00000000',
    avg_entry_price: '1.08540000',
    avg_exit_price: null,
    gross_pnl: '0.00',
    commission: '-0.70',
    swap: '0.10',
    fee: '0.00',
    // У открытой позиции здесь накопленные издержки, а не плавающий результат.
    net_pnl: '-0.60',
    deals_count: 1,
    duration_seconds: null,
    close_reason: null,
    is_manual: false,
    rebuilt_at: '2026-09-07T08:01:00Z',
    account: { id: FIRST_ACCOUNT, label: 'Демо A', color: '#2563eb', is_demo: true },
    journal_entry: null,
    reflection: null,
    attachments_count: 0,
    ...overrides,
  };
}

type Options = {
  accounts?: Account[];
  summary?: Summary;
  days?: CalendarDay[];
  open?: PositionListItem[];
  openCursor?: string | null;
  unreflected?: number;
  unreflectedCursor?: string | null;
  hasReflection?: boolean;
};

type Query = URLSearchParams;

function withDashboard(options: Options = {}): { routes: RouteTable; queries: Query[] } {
  const queries: Query[] = [];
  const accounts = options.accounts ?? [account()];
  const unreflectedItems = Array.from({ length: options.unreflected ?? 0 }, (_, index) =>
    position(500 + index, { status: 'closed', close_time: '2026-09-06T10:00:00Z' }),
  );
  return {
    queries,
    routes: {
      [SESSION]: () => jsonResponse(200, TEST_USER),
      [ACCOUNTS]: ({ url }) => {
        queries.push(url.searchParams);
        return jsonResponse(200, { items: accounts });
      },
      [SUMMARY]: ({ url }) => {
        queries.push(url.searchParams);
        return jsonResponse(200, options.summary ?? summary());
      },
      [CALENDAR]: ({ url }) => {
        queries.push(url.searchParams);
        return jsonResponse(200, calendar(options.days ?? [calendarDay()]));
      },
      [POSITIONS]: ({ url }) => {
        const query = url.searchParams;
        queries.push(query);
        if (query.get('has_reflection') === 'true') {
          return jsonResponse(200, {
            items: options.hasReflection === true ? [position(900)] : [],
            next_cursor: null,
          });
        }
        if (query.get('has_reflection') === 'false') {
          return jsonResponse(200, {
            items: unreflectedItems,
            next_cursor: options.unreflectedCursor ?? null,
          });
        }
        return jsonResponse(200, {
          items: options.open ?? [],
          next_cursor: options.openCursor ?? null,
        });
      },
    },
  };
}

async function openDashboard() {
  const rendered = renderApp(['/']);
  await screen.findByRole('heading', { name: t.pages.dashboard, level: 1 });
  return rendered;
}

function queryFor(queries: Query[], predicate: (query: Query) => boolean): Query {
  const found = queries.find(predicate);
  if (found === undefined) {
    throw new Error('такого запроса не было');
  }
  return found;
}

beforeEach(() => {
  window.localStorage.clear();
  useAccountSelectionStore.setState({ mode: 'all', ids: [] });
});

describe('дашборд: сводка', () => {
  it('показывает числа сервера и не считает своих', async () => {
    installFetchMock(withDashboard().routes);
    await openDashboard();

    expect(await screen.findByText('117,00 $')).toBeInTheDocument();
    // Два знака процента: доля приходит с четырьмя знаками, и разряд, на который сервер
    // отвечает данными, экран терять не должен (docs/metrics.md §3.2).
    expect(screen.getByText('50,00 %')).toBeInTheDocument();
    expect(screen.getByText('2,17')).toBeInTheDocument();
    expect(screen.getByText('14,63 $')).toBeInTheDocument();
  });

  it('при открытых позициях называет их число и объясняет расхождение с журналом', async () => {
    installFetchMock(withDashboard().routes);
    await openDashboard();

    expect(await screen.findByText(t.dashboard.openInPeriod(2))).toBeInTheDocument();
    expect(screen.getByText(t.dashboard.openInPeriodHint)).toBeInTheDocument();
    // Точное совпадение с журналом даёт фильтр «Закрытые» — ссылка ведёт именно туда.
    const link = screen.getByRole('link', { name: t.dashboard.openInPeriodLink });
    expect(link).toHaveAttribute('href', '/journal?period=month&status=closed');
  });

  it('при нуле открытых обещает совпадение до копейки', async () => {
    installFetchMock(withDashboard({ summary: summary({ open_positions: 0 }) }).routes);
    await openDashboard();

    expect(await screen.findByText(t.dashboard.noOpenInPeriod)).toBeInTheDocument();
    expect(screen.queryByText(t.dashboard.openInPeriodHint)).not.toBeInTheDocument();
  });

  it('период сводки и период ссылки в журнал — один и тот же', async () => {
    const { routes, queries } = withDashboard();
    installFetchMock(routes);
    await openDashboard();

    await screen.findByText('117,00 $');
    const asked = queryFor(queries, (query) => query.has('from') && !query.has('status'));
    // Тридцать дней в зоне пользователя: 30 дней по 24 часа от начала торгового дня.
    const from = new Date(asked.get('from') ?? '');
    expect(Number.isNaN(from.getTime())).toBe(false);
  });
});

describe('дашборд: календарь-мини', () => {
  it('день открывает журнал границами сервера и только закрытыми', async () => {
    installFetchMock(withDashboard().routes);
    await openDashboard();

    const link = await screen.findByRole('link', { name: /7 число/ });
    expect(link).toHaveAttribute(
      'href',
      '/journal?from=2026-09-06T19%3A00%3A00Z&to=2026-09-07T19%3A00%3A00Z&status=closed',
    );
  });

  it('день без сделок ссылкой не становится: границ у него нет', async () => {
    installFetchMock(withDashboard().routes);
    await openDashboard();

    await screen.findByRole('link', { name: /7 число/ });
    expect(screen.queryByRole('link', { name: /8 число/ })).not.toBeInTheDocument();
  });

  it('месяц без сделок объяснён словами, и сетка остаётся на месте', async () => {
    installFetchMock(withDashboard({ days: [] }).routes);
    await openDashboard();

    // Сетка без единой суммы читается как «не загрузилось», поэтому рядом стоит фраза.
    // Убирать сам месяц незачем: он показывает, за какой период сказано «сделок нет».
    expect(await screen.findByText(t.dashboard.calendarEmpty)).toBeInTheDocument();
    expect(screen.getByRole('table', { name: /сентябрь 2026/i })).toBeInTheDocument();
  });

  it('на узком экране месяц показан списком: сумма дня видна целиком', async () => {
    // `matchMedia` в jsdom нет вовсе, поэтому раскладка подменяется явно — иначе
    // проверялась бы настольная сетка под видом телефона.
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    installFetchMock(withDashboard({ days: [calendarDay({ net_pnl: '-1779.72' })] }).routes);
    await openDashboard();

    // В ячейке сетки шириной с палец эта сумма обрезалась бы до «-1 779,…», а обрезанные
    // деньги читаются как другое число. В строке списка её обрезать нечему.
    expect(await screen.findByText('-1 779,72 $')).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: /сентябрь 2026/i })).not.toBeInTheDocument();
    // День остаётся ссылкой с теми же границами, что прислал сервер.
    expect(screen.getByRole('link', { name: /7 число/ })).toHaveAttribute(
      'href',
      '/journal?from=2026-09-06T19%3A00%3A00Z&to=2026-09-07T19%3A00%3A00Z&status=closed',
    );
  });
});

describe('дашборд: открытые позиции', () => {
  it('показывает факты открытия и не выдумывает текущий результат', async () => {
    installFetchMock(withDashboard({ open: [position(1)] }).routes);
    await openDashboard();

    const block = (await screen.findByText(t.dashboard.openNoProfit)).closest('div');
    expect(block).not.toBeNull();
    expect(screen.getByText('EURUSD')).toBeInTheDocument();
    // `net_pnl` открытой позиции — накопленные издержки; на экране его нет.
    expect(screen.queryByText('-0,60 $')).not.toBeInTheDocument();
  });

  it('два числа открытых на экране названы разными словами', async () => {
    // В сводке «плюс 2 открытых за тот же период», в блоке — все открытые сейчас, и их
    // больше. Оба числа верны, поэтому множество названо в заголовке: без этого экран,
    // который делается ради «не приходить с багом, которого нет», сам даёт такой повод.
    installFetchMock(
      withDashboard({ open: [position(1), position(2)], openCursor: 'next' }).routes,
    );
    await openDashboard();

    expect(await screen.findByText(t.dashboard.openInPeriod(2))).toBeInTheDocument();
    expect(screen.getByText(t.dashboard.openTitle)).toBeInTheDocument();
    expect(screen.getByText(t.dashboard.openMore(OPEN_POSITIONS_LIMIT))).toBeInTheDocument();
  });

  it('пустой список говорит об этом словами', async () => {
    installFetchMock(withDashboard({ open: [] }).routes);
    await openDashboard();

    expect(await screen.findByText(t.dashboard.openEmpty)).toBeInTheDocument();
  });
});

describe('дашборд: требует внимания', () => {
  it('точное число сделок без рефлексии называется, только когда страница уместилась', async () => {
    installFetchMock(withDashboard({ unreflected: 3 }).routes);
    await openDashboard();

    expect(await screen.findByText(t.dashboard.attentionUnreflected(3))).toBeInTheDocument();
    const link = screen.getByRole('link', { name: t.dashboard.attentionUnreflectedLink });
    expect(link).toHaveAttribute('href', '/journal?period=month&status=closed&reflection=none');
  });

  it('когда строк больше страницы, показано «больше N», а не длина страницы', async () => {
    installFetchMock(
      withDashboard({ unreflected: UNREFLECTED_PROBE_LIMIT, unreflectedCursor: 'next' }).routes,
    );
    await openDashboard();

    expect(
      await screen.findByText(t.dashboard.attentionUnreflectedMany(UNREFLECTED_PROBE_LIMIT)),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(t.dashboard.attentionUnreflected(UNREFLECTED_PROBE_LIMIT)),
    ).not.toBeInTheDocument();
  });

  it('счёт в needs_attention показан с причиной сервера, а не с собственным вердиктом', async () => {
    installFetchMock(
      withDashboard({
        accounts: [
          account({ status: 'needs_attention', status_message: 'Неверный пароль инвестора' }),
        ],
      }).routes,
    );
    await openDashboard();

    expect(await screen.findByText('Неверный пароль инвестора')).toBeInTheDocument();
  });

  it('счёт без единого heartbeat помечен фактом, который не требует порога', async () => {
    installFetchMock(
      withDashboard({ accounts: [account({ status: 'pending', last_heartbeat_at: null })] }).routes,
    );
    await openDashboard();

    expect(await screen.findByText(t.accounts.heartbeatNever)).toBeInTheDocument();
  });
});

describe('дашборд: пустое состояние', () => {
  it('новый пользователь видит шаги и не видит метрик', async () => {
    installFetchMock(withDashboard({ accounts: [] }).routes);
    await openDashboard();

    expect(await screen.findByText(t.dashboard.stepAccountTitle)).toBeInTheDocument();
    expect(screen.getByText(t.dashboard.stepCollectorTitle)).toBeInTheDocument();
    expect(screen.getByText(t.dashboard.stepPositionsTitle)).toBeInTheDocument();
    expect(screen.getByText(t.dashboard.stepReflectionTitle)).toBeInTheDocument();
    // Пустых рамок с прочерками нет: их читают как поломку.
    expect(screen.queryByText(t.dashboard.summaryTitle)).not.toBeInTheDocument();
    expect(screen.queryByText(t.dashboard.openTitle)).not.toBeInTheDocument();
    // Ни один шаг не отмечен.
    expect(screen.queryAllByText(t.dashboard.onboardingDone)).toHaveLength(0);
  });

  it('счёт есть, позиций нет: первые галочки стоят, метрик по-прежнему нет', async () => {
    installFetchMock(
      withDashboard({ accounts: [account({ positions_count: 0 })], summary: summary() }).routes,
    );
    await openDashboard();

    const steps = await screen.findByRole('list');
    // Счёт добавлен и коллектор выходил на связь — два факта из четырёх.
    expect(within(steps).getAllByText(t.dashboard.onboardingDone)).toHaveLength(2);
    expect(within(steps).getAllByText(t.dashboard.onboardingPending)).toHaveLength(2);
    expect(screen.queryByText(t.dashboard.summaryTitle)).not.toBeInTheDocument();
  });

  it('после первой рефлексии шагов на экране нет вовсе', async () => {
    installFetchMock(withDashboard({ hasReflection: true }).routes);
    await openDashboard();

    await screen.findByText('117,00 $');
    expect(screen.queryByText(t.dashboard.onboardingTitle)).not.toBeInTheDocument();
  });

  it('снятая рефлексия возвращает шаг: зонд перечитывает ответ, а не помнит первый', async () => {
    const options: Options = { hasReflection: true };
    installFetchMock(withDashboard(options).routes);
    const { client } = await openDashboard();

    await screen.findByText('117,00 $');
    expect(screen.queryByText(t.dashboard.onboardingTitle)).not.toBeInTheDocument();

    // `filled_at` снимается, если рефлексию очистили целиком (`S2-02`). После
    // инвалидации экран обязан увидеть это, а не остаться с первым ответом.
    options.hasReflection = false;
    await act(async () => {
      await client.invalidateQueries();
    });

    expect(await screen.findByText(t.dashboard.onboardingTitle)).toBeInTheDocument();
    expect(screen.getByText(t.dashboard.stepReflectionTitle)).toBeInTheDocument();
  });

  it('счетов в работе не осталось: архивный и удалённый в список не приходят', async () => {
    // Архивный счёт сервер не отдаёт без `include_archived`, удалённого нет вовсе, —
    // и человек с одним таким счётом снова видит первый шаг. Это верно: архивный счёт
    // сделок не приносит, коллектор его уже не видит (SPEC.md 5.6).
    const { routes, queries } = withDashboard({ accounts: [] });
    installFetchMock(routes);
    await openDashboard();

    expect(await screen.findByText(t.dashboard.stepAccountTitle)).toBeInTheDocument();
    expect(screen.queryAllByText(t.dashboard.onboardingDone)).toHaveLength(0);
    expect(screen.queryByText(t.dashboard.summaryTitle)).not.toBeInTheDocument();
    // Архивные не запрашиваются намеренно: галочка от них не встанет и встать не должна.
    expect(queries.some((query) => query.has('include_archived'))).toBe(false);
  });
});

describe('дашборд: переключатель счетов', () => {
  it('выбранные счета уходят во все запросы экрана', async () => {
    useAccountSelectionStore.setState({ mode: 'single', ids: [SECOND_ACCOUNT] });
    const { routes, queries } = withDashboard({
      accounts: [account(), account({ id: SECOND_ACCOUNT, label: 'Демо B' })],
    });
    installFetchMock(routes);
    await openDashboard();

    await screen.findByText('117,00 $');
    await waitFor(() => {
      expect(
        queries.filter((query) => query.get('account_ids') === SECOND_ACCOUNT).length,
      ).toBeGreaterThanOrEqual(3);
    });
  });

  it('выбор счёта не двигает галочки: онбординг описывает человека, а не выбор', async () => {
    // Выбран пустой счёт, а сделки и связь есть у соседнего. Шаг, снимаемый
    // переключателем, означал бы, что пройденное «отменилось».
    useAccountSelectionStore.setState({ mode: 'single', ids: [SECOND_ACCOUNT] });
    installFetchMock(
      withDashboard({
        accounts: [
          account(),
          account({
            id: SECOND_ACCOUNT,
            label: 'Демо B',
            positions_count: 0,
            last_heartbeat_at: '2026-09-07T09:01:00Z',
          }),
        ],
      }).routes,
    );
    await openDashboard();

    const steps = await screen.findByRole('list');
    expect(within(steps).getAllByText(t.dashboard.onboardingDone)).toHaveLength(3);
    expect(within(steps).getByText(t.dashboard.stepReflectionTitle)).toBeInTheDocument();
  });

  it('список счетов не приехал: метрики показаны по всем счетам, и об этом сказано', async () => {
    const { routes, queries } = withDashboard();
    installFetchMock({
      ...routes,
      [ACCOUNTS]: () => errorResponse(500, 'internal_error', 'сервер не смог'),
    });
    await openDashboard();

    expect(await screen.findByText('117,00 $')).toBeInTheDocument();
    expect(screen.getByText(new RegExp(t.dashboard.loadFailed))).toBeInTheDocument();
    // Запасной вариант — «все счета»: это ровно то, что видно без переключателя, и
    // ничего не прячет. Шагов онбординга при этом нет: на неприехавшем списке все
    // галочки были бы сняты, и человек с двумя счетами прочитал бы «начните со счёта».
    expect(queries.every((query) => !query.has('account_ids'))).toBe(true);
    expect(screen.queryByText(t.dashboard.onboardingTitle)).not.toBeInTheDocument();
  });
});
