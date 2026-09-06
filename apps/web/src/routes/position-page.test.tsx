import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Account } from '@/accounts/api';
import { useAccountSelectionStore } from '@/accounts/selection';
import { t } from '@/i18n';
import type { Deal, JournalEntryDetail, PositionCard, PositionListItem } from '@/journal/api';
import { AUTOSAVE_DELAY_MS } from '@/journal/use-autosave';
import {
  errorResponse,
  installFetchMock,
  jsonResponse,
  type MockedCall,
  type RouteTable,
} from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';

const SESSION = 'GET /api/v1/auth/me';
const ACCOUNTS = 'GET /api/v1/accounts';
const POSITIONS = 'GET /api/v1/journal/positions';
const TAGS = 'GET /api/v1/journal/tags';
const VOCAB = 'GET /api/v1/journal/vocab';

const ACCOUNT_ID = '0199a2b0-0000-7000-8000-0000000000a1';

function positionId(index: number): string {
  return `0199a2b0-0000-7000-8000-${String(index).padStart(12, '0')}`;
}

const CARD_ID = positionId(1);
const CARD = `GET /api/v1/journal/positions/${CARD_ID}`;
const ENTRY = `PUT /api/v1/journal/positions/${CARD_ID}/entry`;
const REFLECTION = `PUT /api/v1/journal/positions/${CARD_ID}/reflection`;

function account(): Account {
  return {
    id: ACCOUNT_ID,
    label: 'Основной',
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
    positions_count: 1,
  };
}

function deal(overrides: Partial<Deal> = {}): Deal {
  return {
    deal_ticket: 700_001,
    order_ticket: 800_001,
    symbol_raw: 'EURUSD.m',
    deal_type: 'buy',
    entry: 'in',
    reason: 'client',
    volume: '0.10000000',
    price: '1.10000000',
    profit: '0.00',
    commission: '-1.00',
    swap: '0.00',
    fee: '0.00',
    time_utc: '2026-09-05T08:00:00Z',
    comment: null,
    magic: null,
    source: 'mt5',
    ...overrides,
  };
}

function card(overrides: Partial<PositionCard> = {}): PositionCard {
  return {
    id: CARD_ID,
    position_id: 100_001,
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
    account: { id: ACCOUNT_ID, label: 'Основной', color: '#2563eb', is_demo: false },
    journal_entry: null,
    reflection: null,
    attachments_count: 0,
    deals: [],
    ...overrides,
  };
}

function listItem(index: number, symbol: string): PositionListItem {
  return {
    id: positionId(index),
    position_id: 100_000 + index,
    symbol_raw: `${symbol}.m`,
    symbol_norm: symbol,
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
    account: { id: ACCOUNT_ID, label: 'Основной', color: '#2563eb', is_demo: false },
    journal_entry: null,
    reflection: null,
    attachments_count: 0,
  };
}

const VOCAB_BODY = {
  emotions: [
    'calm',
    'focused',
    'edgy',
    'fomo',
    'frustrated',
    'bored',
    'euphoric',
    'fearful',
    'tired',
  ],
  mistakes: [
    'no_plan',
    'early_entry',
    'late_entry',
    'chased',
    'moved_sl',
    'no_sl',
    'oversized',
    'revenge',
    'early_exit',
    'held_too_long',
    'against_trend',
    'news_ignored',
    'overtrading',
  ],
  setup_grades: ['A', 'B', 'C', 'D'],
  execution_grades: ['A', 'B', 'C', 'D'],
};

function routesFor(
  position: PositionCard,
  options: { list?: PositionListItem[]; extra?: RouteTable } = {},
): RouteTable {
  return {
    [SESSION]: () => jsonResponse(200, TEST_USER),
    [ACCOUNTS]: () => jsonResponse(200, { items: [account()] }),
    [POSITIONS]: () => jsonResponse(200, { items: options.list ?? [], next_cursor: null }),
    [TAGS]: () => jsonResponse(200, { items: [] }),
    [VOCAB]: () => jsonResponse(200, VOCAB_BODY),
    [CARD]: () => jsonResponse(200, position),
    ...options.extra,
  };
}

/**
 * Содержимое карточки, а не всей страницы: под модалом остаётся журнал, и часть слов
 * («Лонг», «Теги») стоит и в его панели фильтров.
 */
function inCard(): ReturnType<typeof within> | typeof screen {
  const dialog = screen.queryByRole('dialog');
  return dialog === null ? screen : within(dialog);
}

/** Карточка, ответ которой может поменяться между запросами. */
function renderWithCard(next: () => PositionCard) {
  const { calls } = installFetchMock({
    ...routesFor(card()),
    [CARD]: () => jsonResponse(200, next()),
  });
  const { client } = renderApp([`/journal/${CARD_ID}`]);
  return { calls, client };
}

async function openCard(): Promise<void> {
  renderApp([`/journal/${CARD_ID}`]);
  await screen.findByRole('heading', { name: 'EURUSD' });
}

function bodyOf(calls: MockedCall[], path: string): Record<string, unknown> {
  const call = calls.filter((item) => item.path === path).at(-1);
  if (call === undefined) {
    throw new Error(`не было запроса на ${path}`);
  }
  return call.body as Record<string, unknown>;
}

beforeEach(() => {
  window.localStorage.clear();
  useAccountSelectionStore.setState({ mode: 'all', ids: [] });
});

describe('карточка позиции: что видно', () => {
  it('шапка показывает символ, направление, счёт и деньги в формате SPEC.md 9.4', async () => {
    installFetchMock(routesFor(card()));
    await openCard();

    const view = inCard();
    expect(view.getByText('48,00 $')).toBeInTheDocument();
    expect(view.getByText(t.position.long)).toBeInTheDocument();
    expect(view.getByText(/Основной/)).toBeInTheDocument();
    // Время — в зоне пользователя (Asia/Yekaterinburg, UTC+5), а не в UTC.
    expect(view.getByText('05.09.2026 15:30')).toBeInTheDocument();
  });

  it('без риска R не выдумывается: показана причина, а не число', async () => {
    installFetchMock(routesFor(card()));
    await openCard();

    expect(screen.getByText(t.position.ratioUnknown)).toBeInTheDocument();
  });

  it('риск из плана превращается в R по net_pnl', async () => {
    installFetchMock(
      routesFor(
        card({
          journal_entry: {
            notes: null,
            tags: [],
            planned_entry: null,
            planned_sl: null,
            planned_tp: null,
            risk_amount: '32.00',
            updated_at: '2026-09-05T11:00:00Z',
          },
        }),
      ),
    );
    await openCard();

    expect(screen.getByText(t.position.ratioValue('1,50'))).toBeInTheDocument();
  });

  it('пустая таблица сделок объясняет себя, а не выглядит поломкой', async () => {
    installFetchMock(routesFor(card()));
    await openCard();

    expect(screen.getByText(t.position.dealsEmpty)).toBeInTheDocument();
  });

  it('сделки брокера показаны только на чтение', async () => {
    installFetchMock(routesFor(card({ deals: [deal(), deal({ deal_ticket: 700_002 })] })));
    await openCard();

    const deals = screen.getByRole('table');
    expect(within(deals).getAllByRole('row')).toHaveLength(3);
    expect(within(deals).queryByRole('textbox')).not.toBeInTheDocument();
    expect(within(deals).getAllByText('Покупка')).toHaveLength(2);
  });

  it('чужая ссылка объясняет, что позиции нет, и не предлагает повтор', async () => {
    installFetchMock({
      ...routesFor(card()),
      [CARD]: () => errorResponse(404, 'position_not_found', 'нет такой позиции'),
    });
    renderApp([`/journal/${CARD_ID}`]);

    expect(await screen.findByText(t.errors.positionNotFound)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.common.retry })).not.toBeInTheDocument();
  });
});

describe('карточка позиции: автосохранение', () => {
  it('PUT записи журнала несёт все поля тела, а не только изменённое', async () => {
    const { calls } = installFetchMock({
      ...routesFor(card()),
      [ENTRY]: ({ body }) => jsonResponse(200, { ...(body as object), updated_at: 'x' }),
    });
    const user = userEvent.setup();
    await openCard();

    await user.type(screen.getByLabelText(t.position.notesLabel), 'ждал ретест');
    await user.tab();

    await waitFor(() => expect(screen.getAllByText(t.position.saved).length).toBeGreaterThan(0));
    // SPEC.md 5.4: PUT заменяет запись целиком, поэтому частичное тело стёрло бы поля.
    expect(bodyOf(calls, `/api/v1/journal/positions/${CARD_ID}/entry`)).toEqual({
      notes: 'ждал ретест',
      tags: [],
      planned_entry: null,
      planned_sl: null,
      planned_tp: null,
      risk_amount: null,
    });
  });

  it('деньги уходят строкой, а не числом', async () => {
    const { calls } = installFetchMock({
      ...routesFor(card()),
      [ENTRY]: ({ body }) => jsonResponse(200, { ...(body as object), updated_at: 'x' }),
    });
    const user = userEvent.setup();
    await openCard();

    await user.type(screen.getByLabelText(t.position.riskAmount), '32,50');
    await user.tab();

    await waitFor(() => expect(screen.getAllByText(t.position.saved).length).toBeGreaterThan(0));
    const body = bodyOf(calls, `/api/v1/journal/positions/${CARD_ID}/entry`);
    expect(body['risk_amount']).toBe('32.5');
    expect(typeof body['risk_amount']).toBe('string');
  });

  it('обрыв сети показывает ошибку и не теряет набранное', async () => {
    installFetchMock({
      ...routesFor(card()),
      // Не отказ сервера, а несостоявшийся запрос: ровно то, что даёт выключенная сеть.
      [ENTRY]: () => {
        throw new TypeError('Failed to fetch');
      },
    });
    const user = userEvent.setup();
    await openCard();

    const notes = screen.getByLabelText(t.position.notesLabel);
    await user.type(notes, 'мысль, которую жалко потерять');
    await user.tab();

    expect(await screen.findAllByText(t.position.saveFailed)).not.toHaveLength(0);
    expect(screen.getAllByText(t.errors.network).length).toBeGreaterThan(0);
    expect(notes).toHaveValue('мысль, которую жалко потерять');
    expect(screen.queryByText(t.position.saved)).not.toBeInTheDocument();
  });

  it('перечитанная запись подхватывается формой, а не затирается ею', async () => {
    // Найдено в браузере: карточка висела открытой, запись перечиталась (её изменили
    // рядом — другой вкладкой или переименованием тега, SPEC.md 5.4), а форма осталась с
    // прежними значениями и автосохранением записала старое поверх нового.
    let entry: JournalEntryDetail | null = null;
    const { calls, client } = renderWithCard(() => card({ journal_entry: entry }));
    await screen.findByRole('heading', { name: 'EURUSD' });

    entry = {
      notes: 'заметка из соседней вкладки',
      tags: ['Trend'],
      planned_entry: null,
      planned_sl: null,
      planned_tp: null,
      risk_amount: '50.00',
      updated_at: '2026-09-06T10:00:00Z',
    };
    await act(async () => {
      await client.invalidateQueries({ queryKey: ['journal', 'position', CARD_ID] });
    });

    expect(await screen.findByDisplayValue('заметка из соседней вкладки')).toBeInTheDocument();
    expect(inCard().getByText('Trend')).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, AUTOSAVE_DELAY_MS + 200));
    expect(calls.some((call) => call.method === 'PUT')).toBe(false);
  });

  it('в поле плана не число — запрос не уходит вовсе', async () => {
    const { calls } = installFetchMock(routesFor(card()));
    const user = userEvent.setup();
    await openCard();

    await user.type(screen.getByLabelText(t.position.plannedSl), 'около 1,1');
    await user.tab();
    await new Promise((resolve) => setTimeout(resolve, AUTOSAVE_DELAY_MS + 200));

    expect(screen.getByText(t.position.numberInvalid)).toBeInTheDocument();
    expect(calls.some((call) => call.method === 'PUT')).toBe(false);
  });

  it('написание тега берётся из словаря сервера, а не из набранного', async () => {
    installFetchMock({
      ...routesFor(card()),
      // Сервер отвечает написанием словаря: `trend` при заведённом `Trend`.
      [ENTRY]: ({ body }) =>
        jsonResponse(200, { ...(body as object), tags: ['Trend'], updated_at: 'x' }),
    });
    const user = userEvent.setup();
    await openCard();

    await user.type(inCard().getByLabelText(t.position.tagsLabel), 'trend{Enter}');

    expect(await screen.findByText('Trend')).toBeInTheDocument();
    expect(inCard().queryByText('trend')).not.toBeInTheDocument();
  });

  it('рефлексия сохраняется целиком: все поля контракта в одном теле', async () => {
    const { calls } = installFetchMock({
      ...routesFor(card()),
      [REFLECTION]: ({ body }) =>
        jsonResponse(200, {
          ...(body as object),
          filled_at: '2026-09-06T10:00:00Z',
          updated_at: 'x',
        }),
    });
    const user = userEvent.setup();
    await openCard();

    await user.click(
      screen.getByRole('button', { name: t.position.gradeOption(t.position.setupGrade, 'B') }),
    );
    await user.click(screen.getByRole('button', { name: t.position.mistakeLabels.moved_sl }));
    await user.click(screen.getByRole('button', { name: t.position.confidenceOption(4) }));
    await user.selectOptions(
      screen.getByLabelText(t.position.emotionBefore),
      t.position.emotions.fomo,
    );

    await waitFor(() =>
      expect(bodyOf(calls, `/api/v1/journal/positions/${CARD_ID}/reflection`)).toEqual({
        setup_grade: 'B',
        execution_grade: null,
        followed_plan: null,
        emotion_before: 'fomo',
        emotion_during: null,
        emotion_after: null,
        mistakes: ['moved_sl'],
        confidence: 4,
        free_text: null,
      }),
    );
  });
});

describe('карточка позиции: соседи', () => {
  it('стрелки ведут по загруженному списку журнала', async () => {
    installFetchMock(
      routesFor(card(), {
        list: [listItem(0, 'GBPUSD'), listItem(1, 'EURUSD'), listItem(2, 'XAUUSD')],
      }),
    );
    await openCard();

    const prev = screen.getByRole('link', { name: new RegExp(t.position.prev) });
    const next = screen.getByRole('link', { name: new RegExp(t.position.next) });
    expect(prev).toHaveAttribute('href', `/journal/${positionId(0)}`);
    expect(next).toHaveAttribute('href', `/journal/${positionId(2)}`);
  });

  it('позиции нет в загруженном списке — стрелок нет, и сказано почему', async () => {
    installFetchMock(routesFor(card(), { list: [listItem(5, 'GBPUSD')] }));
    await openCard();

    expect(screen.getByText(t.position.neighborsHint)).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: new RegExp(t.position.prev) }),
    ).not.toBeInTheDocument();
  });

  it('фильтры журнала едут в адрес карточки и обратно', async () => {
    installFetchMock(routesFor(card(), { list: [listItem(1, 'EURUSD'), listItem(2, 'XAUUSD')] }));
    renderApp([`/journal/${CARD_ID}?symbol=EURUSD`]);
    await screen.findByRole('heading', { name: 'EURUSD' });

    expect(screen.getByRole('link', { name: t.position.backToJournal })).toHaveAttribute(
      'href',
      '/journal?symbol=EURUSD',
    );
    expect(screen.getByRole('link', { name: new RegExp(t.position.next) })).toHaveAttribute(
      'href',
      `/journal/${positionId(2)}?symbol=EURUSD`,
    );
  });
});

describe('карточка позиции: раскладка', () => {
  it('на большом экране карточка открывается модалом поверх журнала', async () => {
    installFetchMock(routesFor(card(), { list: [listItem(1, 'EURUSD')] }));
    await openCard();

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    // Таблица журнала осталась под модалом: соседей карточка берёт именно из неё.
    expect(screen.getByRole('heading', { name: t.pages.journal })).toBeInTheDocument();
  });

  it('на телефоне это страница, а список под ней не грузится', async () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    const { calls } = installFetchMock(routesFor(card()));
    await openCard();

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: t.pages.journal })).not.toBeInTheDocument();
    expect(calls.some((call) => call.path === '/api/v1/journal/positions')).toBe(false);
  });
});
