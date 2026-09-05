import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { Account, SyncRun } from '@/accounts/api';
import { t } from '@/i18n';
import {
  errorResponse,
  installFetchMock,
  jsonResponse,
  type MockedCall,
  type RouteTable,
} from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';
import { findSecret } from '@/test/secret-probe';

const SESSION = 'GET /api/v1/auth/me';
const LIST = 'GET /api/v1/accounts';

const ACCOUNT_ID = '0199a2b0-0000-7000-8000-0000000000a1';
const ACCOUNT_PATH = `/api/v1/accounts/${ACCOUNT_ID}`;
const PATCH = `PATCH ${ACCOUNT_PATH}`;
const SYNC_RUNS = `GET ${ACCOUNT_PATH}/sync-runs`;

function account(overrides: Partial<Account> = {}): Account {
  return {
    id: ACCOUNT_ID,
    label: 'FTMO Demo',
    is_demo: true,
    color: '#2563eb',
    platform: 'mt5',
    broker: 'FTMO',
    server: 'FTMO-Demo',
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
    positions_count: 7,
    ...overrides,
  };
}

function run(overrides: Partial<SyncRun> = {}): SyncRun {
  return {
    id: 1,
    source: 'collector',
    started_at: '2026-09-02T12:00:00Z',
    finished_at: '2026-09-02T12:00:05Z',
    deals_received: 12,
    deals_new: 3,
    positions_rebuilt: 2,
    server_utc_offset_minutes: 180,
    error: null,
    ...overrides,
  };
}

function withAccount(item: Account | null, extra: RouteTable = {}): RouteTable {
  return {
    [SESSION]: () => jsonResponse(200, TEST_USER),
    [LIST]: () => jsonResponse(200, { items: item === null ? [] : [item] }),
    [SYNC_RUNS]: () => jsonResponse(200, { items: [] }),
    ...extra,
  };
}

function callsTo(calls: MockedCall[], route: string): MockedCall[] {
  return calls.filter((call) => `${call.method} ${call.path}` === route);
}

async function openAccount(): Promise<ReturnType<typeof renderApp>> {
  const rendered = renderApp([`/accounts/${ACCOUNT_ID}`]);
  await screen.findByRole('heading', { level: 1 });
  return rendered;
}

describe('страница счёта', () => {
  it('несуществующий счёт объясняется, а не оставляет пустой экран', async () => {
    installFetchMock(withAccount(null));
    renderApp([`/accounts/${ACCOUNT_ID}`]);

    expect(await screen.findByText(t.account.notFound)).toBeInTheDocument();
  });

  /** Архивный счёт по прямой ссылке обязан открыться: список запрашивается с архивом. */
  it('архивный счёт открывается по ссылке', async () => {
    let archivedRequested: string | null = null;
    installFetchMock({
      [SESSION]: () => jsonResponse(200, TEST_USER),
      [LIST]: ({ url }) => {
        archivedRequested = url.searchParams.get('include_archived');
        return jsonResponse(200, { items: [account({ status: 'archived' })] });
      },
      [SYNC_RUNS]: () => jsonResponse(200, { items: [] }),
    });
    await openAccount();

    expect(await screen.findByText(t.accounts.statusArchived)).toBeInTheDocument();
    expect(archivedRequested).toBe('true');
  });

  it('история синков показывает исход каждого прогона', async () => {
    installFetchMock(
      withAccount(account(), {
        [SYNC_RUNS]: () =>
          jsonResponse(200, {
            items: [
              run({ id: 3, finished_at: null, deals_received: null, deals_new: null }),
              run({ id: 2, error: 'Неверный пароль инвестора' }),
              run({ id: 1 }),
            ],
          }),
      }),
    );
    await openAccount();

    expect(await screen.findByText(t.account.runRunning)).toBeInTheDocument();
    expect(screen.getByText(t.account.runFailed)).toBeInTheDocument();
    expect(screen.getByText('Неверный пароль инвестора')).toBeInTheDocument();
    expect(screen.getByText(t.account.runOk)).toBeInTheDocument();
    // Время прогона — в зоне пользователя (Asia/Yekaterinburg, UTC+5), а не в UTC.
    expect(screen.getAllByText('02.09.2026 17:00')).toHaveLength(3);
  });

  it('пустая история синков объясняет, что синков не было', async () => {
    installFetchMock(withAccount(account()));
    await openAccount();

    expect(await screen.findByText(t.account.syncRunsEmpty)).toBeInTheDocument();
  });

  it('сбой истории синков не ломает остальную страницу', async () => {
    installFetchMock(
      withAccount(account(), {
        [SYNC_RUNS]: () => errorResponse(500, 'internal_error', 'сломалось'),
      }),
    );
    await openAccount();

    expect(await screen.findByText(new RegExp(t.account.syncRunsFailed))).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'FTMO Demo', level: 1 })).toBeInTheDocument();
  });
});

describe('правка счёта', () => {
  /**
   * Присланные `server`, `login` или `password` возвращают счёт в `pending` (контракт
   * S1-06). Значит переименование обязано отправить только `label`: иначе смена подписи
   * останавливала бы работающий синк.
   */
  it('переименование отправляет только label и не трогает доступы', async () => {
    const user = userEvent.setup();
    const { calls } = installFetchMock(
      withAccount(account(), {
        [PATCH]: () => jsonResponse(200, account({ label: 'FTMO Real' })),
      }),
    );
    await openAccount();

    const label = await screen.findByLabelText(t.accounts.labelLabel);
    await user.clear(label);
    await user.type(label, 'FTMO Real');
    await user.click(screen.getByRole('button', { name: t.accounts.save }));

    await waitFor(() => {
      expect(callsTo(calls, PATCH)).toHaveLength(1);
    });
    expect(callsTo(calls, PATCH)[0]?.body).toEqual({ label: 'FTMO Real' });
  });

  it('без изменений сохранять нечего и запрос не уходит', async () => {
    const { calls } = installFetchMock(withAccount(account()));
    await openAccount();

    await screen.findByLabelText(t.accounts.labelLabel);
    expect(screen.getByRole('button', { name: t.accounts.save })).toBeDisabled();
    expect(callsTo(calls, PATCH)).toHaveLength(0);
  });

  it('поле пароля открывается пустым: с сервера он не приходит', async () => {
    installFetchMock(withAccount(account()));
    await openAccount();

    expect(await screen.findByLabelText(t.accounts.passwordLabel)).toHaveValue('');
  });

  /**
   * Форма правки остаётся на экране после сохранения, а её наблюдатель мутации — живым
   * до ухода со страницы. Значит пароль обязан быть стёрт явно во всех местах сразу: в
   * поле, в разметке и в теле мутации, — `findSecret` проверяет каждое отдельно.
   */
  it('после сохранения пароля нет ни в поле, ни в разметке, ни в кэше мутаций', async () => {
    const user = userEvent.setup();
    const password = 'investor-secret-7712';
    const { calls } = installFetchMock(
      withAccount(account(), {
        [PATCH]: () => jsonResponse(200, account()),
      }),
    );
    const { client } = await openAccount();

    await user.type(await screen.findByLabelText(t.accounts.passwordLabel), password);
    expect(findSecret(password, client)).toContain('значение поля account-edit-password');

    await user.click(screen.getByRole('button', { name: t.accounts.save }));

    await waitFor(() => {
      expect(callsTo(calls, PATCH)).toHaveLength(1);
    });
    expect(callsTo(calls, PATCH)[0]?.body).toEqual({ password });
    await waitFor(() => {
      expect(screen.getByLabelText(t.accounts.passwordLabel)).toHaveValue('');
    });
    expect(findSecret(password, client)).toEqual([]);
    // Наблюдатель на странице счёта живёт всю сессию: без явного стирания тело запроса
    // осталось бы в кэше мутаций ровно столько же.
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });

  it('успешное сохранение подтверждается на экране', async () => {
    const user = userEvent.setup();
    const state = { current: account() };
    installFetchMock({
      [SESSION]: () => jsonResponse(200, TEST_USER),
      [LIST]: () => jsonResponse(200, { items: [state.current] }),
      [SYNC_RUNS]: () => jsonResponse(200, { items: [] }),
      [PATCH]: () => {
        state.current = account({ label: 'FTMO Real' });
        return jsonResponse(200, state.current);
      },
    });
    await openAccount();

    const label = await screen.findByLabelText(t.accounts.labelLabel);
    await user.clear(label);
    await user.type(label, 'FTMO Real');
    await user.click(screen.getByRole('button', { name: t.accounts.save }));

    expect(await screen.findByText(t.accounts.saved)).toBeInTheDocument();
  });

  /** Архивный счёт сервер не правит (`422 account_archived`) — формы у него быть не должно. */
  it('у архивного счёта формы правки нет, и сказано почему', async () => {
    installFetchMock(withAccount(account({ status: 'archived' })));
    await openAccount();

    expect(await screen.findByText(t.account.settingsArchived)).toBeInTheDocument();
    expect(screen.queryByLabelText(t.accounts.labelLabel)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.accounts.save })).not.toBeInTheDocument();
  });

  /**
   * Развилка 2 тикета: один и тот же промах приходит двумя кодами. `PATCH` отвечает
   * `422 not_mt5_account`, и объяснение обязано встать у поля пароля, а не только
   * в общей ошибке формы.
   */
  it('422 not_mt5_account объясняется у поля пароля', async () => {
    const user = userEvent.setup();
    installFetchMock(
      withAccount(account(), {
        [PATCH]: () => errorResponse(422, 'not_mt5_account', 'не счёт mt5'),
      }),
    );
    await openAccount();

    await user.type(await screen.findByLabelText(t.accounts.passwordLabel), 'x');
    await user.click(screen.getByRole('button', { name: t.accounts.save }));

    const field = await screen.findByLabelText(t.accounts.passwordLabel);
    await waitFor(() => {
      expect(field).toHaveAttribute('aria-invalid', 'true');
    });
    expect(screen.getByText(t.errors.notMt5Account)).toBeInTheDocument();
  });

  it('400 validation_error встаёт у названного сервером поля', async () => {
    const user = userEvent.setup();
    installFetchMock(
      withAccount(account(), {
        [PATCH]: () =>
          errorResponse(400, 'validation_error', 'проверьте поля', {
            fields: { 'body.login': 'Номер счёта занят другим счётом' },
          }),
      }),
    );
    await openAccount();

    const login = await screen.findByLabelText(t.accounts.loginLabel);
    await user.clear(login);
    await user.type(login, '5009999');
    await user.click(screen.getByRole('button', { name: t.accounts.save }));

    expect(await screen.findByText('Номер счёта занят другим счётом')).toBeInTheDocument();
  });

  it('платформу существующего счёта сменить нельзя', async () => {
    installFetchMock(withAccount(account()));
    await openAccount();

    expect(await screen.findByLabelText(t.accounts.platformLabel)).toBeDisabled();
    expect(screen.getByText(t.accounts.platformHint)).toBeInTheDocument();
  });
});
