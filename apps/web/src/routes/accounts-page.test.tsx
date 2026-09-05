import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { Account } from '@/accounts/api';
import { t } from '@/i18n';
import {
  errorResponse,
  installFetchMock,
  jsonResponse,
  type MockedCall,
  type RouteTable,
} from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';

const SESSION = 'GET /api/v1/auth/me';
const LIST = 'GET /api/v1/accounts';
const CREATE = 'POST /api/v1/accounts';

const ACCOUNT_ID = '0199a2b0-0000-7000-8000-0000000000a1';
const ACCOUNT_PATH = `/api/v1/accounts/${ACCOUNT_ID}`;

/** Счёт из схемы API: поля те же, что придут с сервера, без «удобных» упрощений. */
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
    status: 'pending',
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

function minutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

function withAccounts(items: Account[], extra: RouteTable = {}): RouteTable {
  return {
    [SESSION]: () => jsonResponse(200, TEST_USER),
    [LIST]: () => jsonResponse(200, { items }),
    ...extra,
  };
}

function callsTo(calls: MockedCall[], route: string): MockedCall[] {
  return calls.filter((call) => `${call.method} ${call.path}` === route);
}

async function openAccounts(): Promise<void> {
  renderApp(['/accounts']);
  await screen.findByRole('heading', { name: t.pages.accounts, level: 1 });
}

describe('список счетов', () => {
  it('пустой список объясняет, что делать, а не молчит', async () => {
    installFetchMock(withAccounts([]));
    await openAccounts();

    expect(await screen.findByText(t.accounts.empty)).toBeInTheDocument();
  });

  it('сбой загрузки показан пользователю и даёт повторить', async () => {
    installFetchMock({
      [SESSION]: () => jsonResponse(200, TEST_USER),
      [LIST]: () => errorResponse(500, 'internal_error', 'сломалось'),
    });
    await openAccounts();

    expect(await screen.findByText(new RegExp(t.accounts.loadFailed))).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.common.retry })).toBeEnabled();
  });

  /**
   * Acceptance тикета S1-11: отрисованы все пять состояний. `needs_attention` — вместе с
   * серверным текстом: красный бейдж без причины хуже отсутствия бейджа.
   */
  it('показывает все статусы счёта, включая причину needs_attention и архив', async () => {
    installFetchMock(
      withAccounts([
        account({ id: '1', label: 'Ожидание', status: 'pending' }),
        account({
          id: '2',
          label: 'Рабочий',
          status: 'connected',
          last_sync_at: minutesAgo(2),
          last_heartbeat_at: minutesAgo(1),
        }),
        account({
          id: '3',
          label: 'Сломанный',
          status: 'needs_attention',
          status_message: 'Неверный пароль инвестора',
        }),
        account({ id: '4', label: 'Пауза', status: 'paused' }),
        account({ id: '5', label: 'Архив', status: 'archived' }),
      ]),
    );
    await openAccounts();

    expect(await screen.findByText(t.accounts.statusPending)).toBeInTheDocument();
    expect(screen.getByText(t.accounts.statusConnected)).toBeInTheDocument();
    expect(screen.getByText(t.accounts.statusConnectedHint('2 минуты назад'))).toBeInTheDocument();
    expect(screen.getByText(t.accounts.statusNeedsAttention)).toBeInTheDocument();
    expect(screen.getByText('Неверный пароль инвестора')).toBeInTheDocument();
    expect(screen.getByText(t.accounts.statusPaused)).toBeInTheDocument();
    expect(screen.getByText(t.accounts.statusArchived)).toBeInTheDocument();
  });

  /**
   * Порог «5 минут» живёт на сервере. Здесь проверяется, что фронт его не завёл заново:
   * heartbeat десятиминутной давности — это факт со временем, а не вердикт «не на связи».
   */
  it('heartbeat показан фактом; жёлтое предупреждение — только когда связи не было ни разу', async () => {
    installFetchMock(
      withAccounts([
        account({
          id: '1',
          label: 'Молчит',
          status: 'connected',
          last_heartbeat_at: minutesAgo(10),
        }),
        account({ id: '2', label: 'Ни разу', status: 'pending', last_heartbeat_at: null }),
      ]),
    );
    await openAccounts();

    expect(await screen.findByText(t.accounts.heartbeatLast('10 минут назад'))).toBeInTheDocument();
    expect(screen.getByText(t.accounts.heartbeatNever)).toBeInTheDocument();
  });

  it('счёт «вручную» не обещает коллектор и не предлагает синк', async () => {
    installFetchMock(
      withAccounts([
        account({ platform: 'manual', label: 'Руками', server: null, login: null, broker: null }),
      ]),
    );
    await openAccounts();

    expect(await screen.findByText('Руками')).toBeInTheDocument();
    expect(screen.queryByText(t.accounts.heartbeatNever)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.accounts.sync })).not.toBeInTheDocument();
    expect(screen.getByText(new RegExp(t.accounts.noBroker))).toBeInTheDocument();
  });

  it('показ архивных живёт в адресе и восстанавливается из него', async () => {
    const { calls } = installFetchMock(withAccounts([account({ status: 'archived' })]));
    renderApp(['/accounts?archived=1']);

    const checkbox = await screen.findByLabelText(t.accounts.showArchived);
    expect(checkbox).toBeChecked();
    await waitFor(() => {
      expect(callsTo(calls, LIST)).toHaveLength(1);
    });
    expect(screen.getByText(t.accounts.statusArchived)).toBeInTheDocument();
  });
});

describe('синхронизировать', () => {
  /** `202` — просьба принята, синк ещё не произошёл. Слова «синхронизировано» быть не должно. */
  it('коллектор на связи: обещает скорый синк, но не объявляет его состоявшимся', async () => {
    const user = userEvent.setup();
    installFetchMock(
      withAccounts([account({ status: 'connected', last_heartbeat_at: minutesAgo(1) })], {
        [`POST ${ACCOUNT_PATH}/sync-now`]: () =>
          jsonResponse(202, {
            sync_requested_at: new Date().toISOString(),
            last_sync_at: null,
            last_heartbeat_at: minutesAgo(1),
            collector_online: true,
          }),
      }),
    );
    await openAccounts();

    await user.click(await screen.findByRole('button', { name: t.accounts.sync }));

    expect(await screen.findByText(t.accounts.syncQueuedOnline)).toBeInTheDocument();
    expect(screen.queryByText(/синхронизировано/i)).not.toBeInTheDocument();
  });

  it('коллектор не на связи: просьба сохранена, но синк отложен до его запуска', async () => {
    const user = userEvent.setup();
    installFetchMock(
      withAccounts([account({ status: 'connected', last_heartbeat_at: minutesAgo(30) })], {
        [`POST ${ACCOUNT_PATH}/sync-now`]: () =>
          jsonResponse(202, {
            sync_requested_at: new Date().toISOString(),
            last_sync_at: null,
            last_heartbeat_at: minutesAgo(30),
            collector_online: false,
          }),
      }),
    );
    await openAccounts();

    await user.click(await screen.findByRole('button', { name: t.accounts.sync }));

    expect(await screen.findByText(t.accounts.syncQueuedOffline)).toBeInTheDocument();
  });

  it('на паузе синк не просится, и сказано почему', async () => {
    installFetchMock(withAccounts([account({ status: 'paused' })]));
    await openAccounts();

    expect(await screen.findByRole('button', { name: t.accounts.sync })).toBeDisabled();
    expect(screen.getByText(t.accounts.syncDisabledPaused)).toBeInTheDocument();
  });

  it('серверная ошибка синка показана человеку', async () => {
    const user = userEvent.setup();
    installFetchMock(
      withAccounts([account({ status: 'connected' })], {
        [`POST ${ACCOUNT_PATH}/sync-now`]: () =>
          errorResponse(422, 'account_paused', 'счёт на паузе'),
      }),
    );
    await openAccounts();

    await user.click(await screen.findByRole('button', { name: t.accounts.sync }));

    expect(await screen.findByText(new RegExp(t.accounts.syncFailed))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(t.errors.accountPaused))).toBeInTheDocument();
  });
});

describe('удаление счёта', () => {
  async function openDeleteDialog(positionsCount = 42): Promise<{ calls: MockedCall[] }> {
    const user = userEvent.setup();
    const mock = installFetchMock(
      withAccounts([account({ positions_count: positionsCount })], {
        [`DELETE ${ACCOUNT_PATH}`]: () => new Response(null, { status: 204 }),
      }),
    );
    await openAccounts();
    await user.click(await screen.findByRole('button', { name: t.accounts.delete }));
    return mock;
  }

  it('перечисляет, что именно теряется, а не просто просит слово', async () => {
    await openDeleteDialog(42);

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(t.accounts.deleteLead)).toBeInTheDocument();
    expect(within(dialog).getByText(t.accounts.deleteLossDeals)).toBeInTheDocument();
    expect(within(dialog).getByText(t.accounts.deleteLossPositions(42))).toBeInTheDocument();
    expect(within(dialog).getByText(t.accounts.deleteLossReflections)).toBeInTheDocument();
    expect(within(dialog).getByText(t.accounts.deleteAlternative)).toBeInTheDocument();
  });

  it('неверное имя не удаляет ничего и говорит об этом', async () => {
    const user = userEvent.setup();
    const { calls } = await openDeleteDialog();

    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByRole('textbox'), 'ftmo demo');
    await user.click(within(dialog).getByRole('button', { name: t.accounts.deleteConfirm }));

    expect(await screen.findByText(t.accounts.deleteConfirmMismatch)).toBeInTheDocument();
    expect(callsTo(calls, `DELETE ${ACCOUNT_PATH}`)).toHaveLength(0);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('точное имя удаляет счёт', async () => {
    const user = userEvent.setup();
    const { calls } = await openDeleteDialog();

    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByRole('textbox'), 'FTMO Demo');
    await user.click(within(dialog).getByRole('button', { name: t.accounts.deleteConfirm }));

    await waitFor(() => {
      expect(callsTo(calls, `DELETE ${ACCOUNT_PATH}`)).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('«Отмена» закрывает окно и ничего не отправляет', async () => {
    const user = userEvent.setup();
    const { calls } = await openDeleteDialog();

    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByRole('textbox'), 'FTMO Demo');
    await user.click(within(dialog).getByRole('button', { name: t.common.cancel }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(callsTo(calls, `DELETE ${ACCOUNT_PATH}`)).toHaveLength(0);
  });
});

describe('добавление счёта', () => {
  const PASSWORD = 'investor-secret-9134';

  async function fillCreateForm(): Promise<{ calls: MockedCall[] }> {
    const user = userEvent.setup();
    const mock = installFetchMock(
      withAccounts([], {
        [CREATE]: () => jsonResponse(201, account({ label: 'Новый', status: 'pending' })),
      }),
    );
    await openAccounts();

    await user.click(screen.getByRole('button', { name: t.accounts.add }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(t.accounts.labelLabel), 'Новый');
    await user.type(within(dialog).getByLabelText(t.accounts.serverLabel), 'FTMO-Demo');
    await user.type(within(dialog).getByLabelText(t.accounts.loginLabel), '5001234');
    await user.type(within(dialog).getByLabelText(t.accounts.passwordLabel), PASSWORD);
    return mock;
  }

  it('объясняет, почему нужен именно инвесторский пароль', async () => {
    const user = userEvent.setup();
    installFetchMock(withAccounts([]));
    await openAccounts();

    await user.click(screen.getByRole('button', { name: t.accounts.add }));
    const dialog = await screen.findByRole('dialog');

    expect(within(dialog).getByText(t.accounts.passwordWhy)).toBeInTheDocument();
    expect(within(dialog).getByText(t.accounts.passwordWhere)).toBeInTheDocument();
    expect(within(dialog).getByText(t.accounts.passwordNeverMain)).toBeInTheDocument();
  });

  /**
   * Acceptance тикета: пароль не должен остаться в DOM после сохранения. Проверяется
   * фактом — поиском значения по разметке страницы, а не рассуждением о том, что форма
   * размонтирована.
   */
  it('после сохранения пароль не остаётся в разметке страницы', async () => {
    const user = userEvent.setup();
    const { calls } = await fillCreateForm();

    // До отправки пароль в поле есть — иначе проверка после отправки ничего не значит.
    expect(document.body.innerHTML).toContain(PASSWORD);

    await user.click(screen.getByRole('button', { name: t.accounts.create }));

    await waitFor(() => {
      expect(callsTo(calls, CREATE)).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(document.body.innerHTML).not.toContain(PASSWORD);
  });

  it('пароль уходит в теле запроса и не попадает в адрес', async () => {
    const user = userEvent.setup();
    const { calls } = await fillCreateForm();

    await user.click(screen.getByRole('button', { name: t.accounts.create }));

    await waitFor(() => {
      expect(callsTo(calls, CREATE)).toHaveLength(1);
    });
    const [created] = callsTo(calls, CREATE);
    expect(created?.body).toMatchObject({
      label: 'Новый',
      platform: 'mt5',
      server: 'FTMO-Demo',
      login: 5_001_234,
      password: PASSWORD,
    });
    expect(window.location.search).not.toContain(PASSWORD);
  });

  it('незаполненные поля MT5 останавливают отправку', async () => {
    const user = userEvent.setup();
    const { calls } = installFetchMock(withAccounts([]));
    await openAccounts();

    await user.click(screen.getByRole('button', { name: t.accounts.add }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: t.accounts.create }));

    expect(await screen.findByText(t.accounts.formLabelRequired)).toBeInTheDocument();
    expect(screen.getByText(t.accounts.formServerRequired)).toBeInTheDocument();
    expect(screen.getByText(t.accounts.formLoginRequired)).toBeInTheDocument();
    expect(screen.getByText(t.accounts.formPasswordRequired)).toBeInTheDocument();
    expect(callsTo(calls, CREATE)).toHaveLength(0);
  });

  it('у счёта «вручную» полей MT5 нет вовсе', async () => {
    const user = userEvent.setup();
    installFetchMock(withAccounts([]));
    await openAccounts();

    await user.click(screen.getByRole('button', { name: t.accounts.add }));
    const dialog = await screen.findByRole('dialog');
    await user.selectOptions(within(dialog).getByLabelText(t.accounts.platformLabel), 'manual');

    expect(within(dialog).queryByLabelText(t.accounts.passwordLabel)).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText(t.accounts.serverLabel)).not.toBeInTheDocument();
  });

  it('серверная ошибка создания показана и не закрывает форму', async () => {
    const user = userEvent.setup();
    installFetchMock(
      withAccounts([], {
        [CREATE]: () => errorResponse(409, 'account_already_exists', 'уже есть'),
      }),
    );
    await openAccounts();

    await user.click(screen.getByRole('button', { name: t.accounts.add }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(t.accounts.labelLabel), 'Новый');
    await user.type(within(dialog).getByLabelText(t.accounts.serverLabel), 'FTMO-Demo');
    await user.type(within(dialog).getByLabelText(t.accounts.loginLabel), '5001234');
    await user.type(within(dialog).getByLabelText(t.accounts.passwordLabel), 'x');
    await user.click(within(dialog).getByRole('button', { name: t.accounts.create }));

    expect(await screen.findByText(new RegExp(t.accounts.createFailed))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(t.errors.accountAlreadyExists))).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});
