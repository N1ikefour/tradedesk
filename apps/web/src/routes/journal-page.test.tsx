import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Account } from '@/accounts/api';
import { useAccountSelectionStore } from '@/accounts/selection';
import { t } from '@/i18n';
import type { PositionListItem } from '@/journal/api';
import { errorResponse, installFetchMock, jsonResponse, type RouteTable } from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';

const SESSION = 'GET /api/v1/auth/me';
const ACCOUNTS = 'GET /api/v1/accounts';
const POSITIONS = 'GET /api/v1/journal/positions';

const FIRST_ACCOUNT = '0199a2b0-0000-7000-8000-0000000000a1';
const SECOND_ACCOUNT = '0199a2b0-0000-7000-8000-0000000000a2';

function account(id: string, label: string): Account {
  return {
    id,
    label,
    is_demo: false,
    color: '#2563eb',
    platform: 'mt5',
    broker: null,
    server: 'Broker-Live',
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
  };
}

/** Позиция из схемы API: те же поля, что придут с сервера. */
function position(index: number, overrides: Partial<PositionListItem> = {}): PositionListItem {
  const id = `0199a2b0-0000-7000-8000-${String(index).padStart(12, '0')}`;
  return {
    id,
    position_id: 100_000 + index,
    symbol_raw: 'EURUSD.m',
    symbol_norm: 'EURUSD',
    direction: 'long',
    status: 'closed',
    result: 'win',
    open_time: '2026-09-05T08:00:00Z',
    close_time: '2026-09-05T10:30:00Z',
    volume_opened: '0.10000000',
    volume_closed: '0.10000000',
    avg_entry_price: '1.10000000',
    avg_exit_price: '1.10500000',
    gross_pnl: '50.00',
    commission: '-2.00',
    swap: '0.00',
    fee: '0.00',
    net_pnl: '48.00',
    deals_count: 2,
    duration_seconds: 9000,
    close_reason: null,
    is_manual: false,
    rebuilt_at: '2026-09-05T10:31:00Z',
    account: { id: FIRST_ACCOUNT, label: 'Основной', color: '#2563eb', is_demo: false },
    journal_entry: null,
    reflection: null,
    attachments_count: 0,
    ...overrides,
  };
}

type Query = URLSearchParams;

function withJournal(
  items: PositionListItem[],
  options: { accounts?: Account[]; nextCursor?: string | null } = {},
): { routes: RouteTable; queries: Query[] } {
  const queries: Query[] = [];
  const accounts = options.accounts ?? [account(FIRST_ACCOUNT, 'Основной')];
  return {
    queries,
    routes: {
      [SESSION]: () => jsonResponse(200, TEST_USER),
      [ACCOUNTS]: () => jsonResponse(200, { items: accounts }),
      [POSITIONS]: ({ url }) => {
        queries.push(url.searchParams);
        return jsonResponse(200, { items, next_cursor: options.nextCursor ?? null });
      },
    },
  };
}

function lastQuery(queries: Query[]): Query {
  const query = queries[queries.length - 1];
  if (query === undefined) {
    throw new Error('журнал не запрашивался ни разу');
  }
  return query;
}

async function openJournal(entries: string[] = ['/journal']) {
  const rendered = renderApp(entries);
  await screen.findByRole('heading', { name: t.pages.journal, level: 1 });
  return rendered;
}

beforeEach(() => {
  window.localStorage.clear();
  useAccountSelectionStore.setState({ mode: 'all', ids: [] });
});

describe('журнал: список', () => {
  it('показывает позицию так, как её описывает SPEC.md 9.3', async () => {
    const { routes } = withJournal([position(1)]);
    installFetchMock(routes);
    await openJournal();

    await screen.findByText('EURUSD');
    // Смотрим в таблицу, а не на всю страницу: те же слова стоят в списках фильтров.
    const table = within(screen.getByRole('table'));

    expect(table.getByText('EURUSD')).toBeInTheDocument();
    expect(table.getByText(t.journal.long)).toBeInTheDocument();
    // Деньги — по SPEC.md 9.4, из строки и без превращения в число.
    // Пробел здесь обычный: Testing Library схлопывает неразрывный при сравнении.
    expect(table.getByText('48,00 $')).toBeInTheDocument();
    // Время — в зоне пользователя (Asia/Yekaterinburg, UTC+5), а не в UTC.
    expect(table.getByText('05.09.2026 15:30')).toBeInTheDocument();
    expect(table.getByText('2 ч 30 мин')).toBeInTheDocument();
  });

  it('открытая позиция видна и помечена, а не выглядит потерянной', async () => {
    const { routes } = withJournal([
      position(1, {
        status: 'open',
        result: null,
        close_time: null,
        duration_seconds: null,
        avg_exit_price: null,
        symbol_norm: 'XAUUSD',
      }),
    ]);
    installFetchMock(routes);
    await openJournal();

    expect(await screen.findByText('XAUUSD')).toBeInTheDocument();
    expect(screen.getByText(t.journal.stillOpen)).toBeInTheDocument();
  });

  it('R считается по плану, а без плана столбец пуст', async () => {
    const { routes } = withJournal([
      position(1, {
        net_pnl: '150.00',
        journal_entry: {
          tags: ['news'],
          has_notes: false,
          notes_preview: null,
          risk_amount: '100.00',
          updated_at: '2026-09-05T11:00:00Z',
        },
      }),
      position(2, { symbol_norm: 'GBPUSD' }),
    ]);
    installFetchMock(routes);
    await openJournal();

    expect(await screen.findByText('1,50')).toBeInTheDocument();
    expect(screen.getByText('news')).toBeInTheDocument();
  });

  it('общего числа строк не обещает: показывает загруженное и конец списка', async () => {
    const { routes } = withJournal([position(1), position(2)]);
    installFetchMock(routes);
    await openJournal();

    expect(await screen.findByText(t.journal.loadedCount(2))).toBeInTheDocument();
    expect(screen.getByText(t.journal.allLoaded)).toBeInTheDocument();
  });

  it('следующая страница догружается по курсору, а не по номеру', async () => {
    const first = [position(1)];
    const queries: Query[] = [];
    installFetchMock({
      [SESSION]: () => jsonResponse(200, TEST_USER),
      [ACCOUNTS]: () => jsonResponse(200, { items: [account(FIRST_ACCOUNT, 'Основной')] }),
      [POSITIONS]: ({ url }) => {
        queries.push(url.searchParams);
        const cursor = url.searchParams.get('cursor');
        return cursor === null
          ? jsonResponse(200, { items: first, next_cursor: 'cursor-2' })
          : jsonResponse(200, {
              items: [position(2, { symbol_norm: 'GBPUSD' })],
              next_cursor: null,
            });
      },
    });
    await openJournal();

    expect(await screen.findByText('GBPUSD')).toBeInTheDocument();
    expect(queries[1]?.get('cursor')).toBe('cursor-2');
    expect(lastQuery(queries).has('page')).toBe(false);
  });
});

describe('журнал: пустые состояния', () => {
  it('без позиций объясняет, откуда они берутся', async () => {
    const { routes } = withJournal([]);
    installFetchMock(routes);
    await openJournal();

    expect(await screen.findByText(t.journal.empty)).toBeInTheDocument();
    expect(screen.getByText(t.journal.emptyHint)).toBeInTheDocument();
  });

  it('без счетов ведёт к счетам, а не жалуется на пустоту', async () => {
    const { routes } = withJournal([], { accounts: [] });
    installFetchMock(routes);
    await openJournal();

    expect(await screen.findByText(t.journal.emptyAccounts)).toBeInTheDocument();
  });

  it('пустой результат фильтра — другое состояние, и его можно снять', async () => {
    const { routes } = withJournal([]);
    installFetchMock(routes);
    await openJournal(['/journal?symbol=EURUSD']);

    expect(await screen.findByText(t.journal.emptyFiltered)).toBeInTheDocument();

    const panel = within(screen.getByRole('form', { name: t.journal.filtersTitle }));
    await userEvent.click(panel.getByRole('button', { name: t.journal.resetFilters }));

    await waitFor(() => expect(screen.getByText(t.journal.empty)).toBeInTheDocument());
  });

  it('ошибка сервера показана человеку и повторяется кнопкой', async () => {
    let attempt = 0;
    installFetchMock({
      [SESSION]: () => jsonResponse(200, TEST_USER),
      [ACCOUNTS]: () => jsonResponse(200, { items: [account(FIRST_ACCOUNT, 'Основной')] }),
      [POSITIONS]: () => {
        attempt += 1;
        return attempt === 1
          ? errorResponse(500, 'internal_error', 'сервер не смог')
          : jsonResponse(200, { items: [position(1)], next_cursor: null });
      },
    });
    await openJournal();

    expect(await screen.findByRole('alert')).toHaveTextContent(t.journal.loadFailed);

    await userEvent.click(screen.getByRole('button', { name: t.common.retry }));

    expect(await screen.findByText('EURUSD')).toBeInTheDocument();
  });
});

describe('журнал: фильтры в адресе', () => {
  it('фильтр из адреса восстанавливается на экране и в запросе', async () => {
    const { routes, queries } = withJournal([position(1)]);
    installFetchMock(routes);
    await openJournal(['/journal?symbol=EURUSD&result=win&direction=long&period=week']);

    await waitFor(() => expect(queries.length).toBeGreaterThan(0));
    const query = lastQuery(queries);

    expect(query.get('symbol')).toBe('EURUSD');
    expect(query.get('result')).toBe('win');
    expect(query.get('direction')).toBe('long');
    expect(query.get('from')).not.toBeNull();

    expect(screen.getByLabelText(t.journal.symbolLabel)).toHaveValue('EURUSD');
    expect(screen.getByLabelText(t.journal.resultLabel)).toHaveValue('win');
  });

  it('испорченный параметр не роняет экран и не уезжает на сервер', async () => {
    const { routes, queries } = withJournal([position(1)]);
    installFetchMock(routes);
    await openJournal([
      '/journal?direction=diagonal&sort=DROP%20TABLE&result=%D0%B4%D0%B0&utm_source=telegram',
    ]);

    expect(await screen.findByText('EURUSD')).toBeInTheDocument();

    const query = lastQuery(queries);
    expect(query.get('direction')).toBeNull();
    expect(query.get('result')).toBeNull();
    expect(query.get('utm_source')).toBeNull();
    expect(query.get('sort')).toBe('close_time:desc');
  });

  it('изменение фильтра переезжает в адрес — оттуда его и восстанавливает перезагрузка', async () => {
    const { routes, queries } = withJournal([position(1)]);
    installFetchMock(routes);
    const { unmount } = await openJournal();

    await userEvent.type(screen.getByLabelText(t.journal.symbolLabel), 'XAUUSD');
    await userEvent.click(screen.getByRole('button', { name: t.journal.apply }));

    await waitFor(() => expect(lastQuery(queries).get('symbol')).toBe('XAUUSD'));

    // Перезагрузка страницы: приложение поднимается заново по тому же адресу.
    unmount();
    await openJournal(['/journal?symbol=XAUUSD']);

    expect(screen.getByLabelText(t.journal.symbolLabel)).toHaveValue('XAUUSD');
    await waitFor(() => expect(lastQuery(queries).get('symbol')).toBe('XAUUSD'));
  });

  it('сортировка меняется кликом по заголовку столбца', async () => {
    const { routes, queries } = withJournal([position(1)]);
    installFetchMock(routes);
    await openJournal();

    await screen.findByText('EURUSD');
    await userEvent.click(
      screen.getByRole('button', { name: t.journal.sortBy(t.journal.columnNetPnl) }),
    );

    await waitFor(() => expect(lastQuery(queries).get('sort')).toBe('net_pnl:desc'));
  });
});

describe('журнал: переключатель счетов', () => {
  it('выбор счёта уходит в account_ids и перезапрашивает список', async () => {
    const { routes, queries } = withJournal([position(1)], {
      accounts: [account(FIRST_ACCOUNT, 'Основной'), account(SECOND_ACCOUNT, 'Второй')],
    });
    installFetchMock(routes);
    await openJournal();

    await waitFor(() => expect(lastQuery(queries).has('account_ids')).toBe(false));

    await userEvent.click(screen.getByRole('button', { name: t.accountSwitcher.open }));
    await userEvent.click(screen.getByRole('checkbox', { name: /Второй/ }));

    await waitFor(() => expect(lastQuery(queries).get('account_ids')).toBe(SECOND_ACCOUNT));
  });

  it('единственный счёт показан без выпадающего списка', async () => {
    const { routes } = withJournal([position(1)]);
    installFetchMock(routes);
    await openJournal();

    expect(await screen.findByText('Основной')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.accountSwitcher.open })).not.toBeInTheDocument();
  });
});

describe('журнал: мобильная раскладка', () => {
  it('узкий экран показывает карточки, а не таблицу', async () => {
    // `matchMedia` в jsdom нет вовсе, поэтому раскладка подменяется явно: без подмены
    // проверялся бы настольный вариант под видом мобильного.
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    const { routes } = withJournal([position(1)]);
    installFetchMock(routes);
    await openJournal();

    expect(await screen.findByText('EURUSD')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    // Те же данные, что в таблице: символ, итог, время закрытия.
    expect(screen.getByText('48,00 $')).toBeInTheDocument();
    expect(screen.getByText('05.09.2026 15:30')).toBeInTheDocument();
  });
});

describe('журнал: виртуализация', () => {
  it('пять тысяч позиций не превращаются в пять тысяч строк разметки', async () => {
    const items = Array.from({ length: 5000 }, (_, index) => position(index + 1));
    const { routes } = withJournal(items);
    installFetchMock(routes);
    await openJournal();

    await screen.findByText(t.journal.loadedCount(5000));
    const rows = screen.getAllByRole('link', { name: /^Открыть позицию/ });

    // Окно прокрутки плюс запас — десятки строк, а не тысячи. Точное число зависит от
    // высоты окна, поэтому проверяется порядок величины, а не константа.
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(100);
  });
});
