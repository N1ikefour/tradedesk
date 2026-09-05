import type { QueryClient } from '@tanstack/react-query';
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
  type MockRoute,
  type RouteTable,
} from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';
import { findSecret } from '@/test/secret-probe';

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

async function openAccounts(): Promise<ReturnType<typeof renderApp>> {
  const rendered = renderApp(['/accounts']);
  await screen.findByRole('heading', { name: t.pages.accounts, level: 1 });
  return rendered;
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

describe('пауза и возобновление', () => {
  const PAUSE = `POST ${ACCOUNT_PATH}/pause`;
  const RESUME = `POST ${ACCOUNT_PATH}/resume`;

  /** Список после мутации перезапрашивается — статус на кнопке обязан прийти с сервера. */
  function changingStatus(initial: Account['status']) {
    const state = { status: initial };
    const routes: RouteTable = {
      [SESSION]: () => jsonResponse(200, TEST_USER),
      [LIST]: () => jsonResponse(200, { items: [account({ status: state.status })] }),
    };
    return { state, routes };
  }

  it('пауза уходит на сервер, и кнопка становится возобновлением', async () => {
    const user = userEvent.setup();
    const { state, routes } = changingStatus('connected');
    const { calls } = installFetchMock({
      ...routes,
      [PAUSE]: () => {
        state.status = 'paused';
        return jsonResponse(200, account({ status: 'paused' }));
      },
    });
    await openAccounts();

    await user.click(await screen.findByRole('button', { name: t.accounts.pause }));

    await waitFor(() => {
      expect(callsTo(calls, PAUSE)).toHaveLength(1);
    });
    expect(await screen.findByRole('button', { name: t.accounts.resume })).toBeInTheDocument();
    expect(screen.getByText(t.accounts.statusPaused)).toBeInTheDocument();
  });

  it('возобновление возвращает счёт в работу', async () => {
    const user = userEvent.setup();
    const { state, routes } = changingStatus('paused');
    const { calls } = installFetchMock({
      ...routes,
      [RESUME]: () => {
        state.status = 'connected';
        return jsonResponse(200, account({ status: 'connected' }));
      },
    });
    await openAccounts();

    await user.click(await screen.findByRole('button', { name: t.accounts.resume }));

    await waitFor(() => {
      expect(callsTo(calls, RESUME)).toHaveLength(1);
    });
    expect(await screen.findByRole('button', { name: t.accounts.pause })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.accounts.sync })).toBeEnabled();
  });

  it('серверная ошибка паузы показана человеку', async () => {
    const user = userEvent.setup();
    installFetchMock(
      withAccounts([account({ status: 'connected' })], {
        [PAUSE]: () => errorResponse(422, 'account_archived', 'счёт в архиве'),
      }),
    );
    await openAccounts();

    await user.click(await screen.findByRole('button', { name: t.accounts.pause }));

    expect(await screen.findByText(new RegExp(t.accounts.pauseFailed))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(t.errors.accountArchived))).toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.accounts.pause })).toBeEnabled();
  });
});

/**
 * Архивирование необратимо и удаляет пароль с сервера (SPEC.md 5.2): его исходы стоят
 * тестов не меньше удаления, хоть журнал и остаётся на месте.
 */
describe('архивирование счёта', () => {
  const ARCHIVE = `POST ${ACCOUNT_PATH}/archive`;

  async function openArchiveDialog(extra: RouteTable): Promise<{ calls: MockedCall[] }> {
    const user = userEvent.setup();
    const mock = installFetchMock(withAccounts([account({ status: 'connected' })], extra));
    await openAccounts();
    await user.click(await screen.findByRole('button', { name: t.accounts.archive }));
    await screen.findByRole('dialog');
    return mock;
  }

  it('называет цену архива и предлагает паузу как обратимую альтернативу', async () => {
    await openArchiveDialog({});

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(t.accounts.archiveBody)).toBeInTheDocument();
    expect(within(dialog).getByText(t.accounts.archiveIrreversible)).toBeInTheDocument();
  });

  it('подтверждение архивирует счёт и уводит его из списка по умолчанию', async () => {
    const user = userEvent.setup();
    let archived = false;
    const { calls } = installFetchMock({
      [SESSION]: () => jsonResponse(200, TEST_USER),
      // Архивные в выдачу по умолчанию не попадают — это делает сервер, не фронт.
      [LIST]: () =>
        jsonResponse(200, { items: archived ? [] : [account({ status: 'connected' })] }),
      [ARCHIVE]: () => {
        archived = true;
        return jsonResponse(200, account({ status: 'archived' }));
      },
    });
    await openAccounts();

    await user.click(await screen.findByRole('button', { name: t.accounts.archive }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: t.accounts.archiveConfirm }));

    await waitFor(() => {
      expect(callsTo(calls, ARCHIVE)).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(await screen.findByText(t.accounts.empty)).toBeInTheDocument();
  });

  it('серверная ошибка показана, окно остаётся открытым', async () => {
    const user = userEvent.setup();
    const { calls } = await openArchiveDialog({
      [ARCHIVE]: () => errorResponse(422, 'account_archived', 'уже в архиве'),
    });

    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: t.accounts.archiveConfirm }));

    expect(await screen.findByText(new RegExp(t.accounts.archiveFailed))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(t.errors.accountArchived))).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(callsTo(calls, ARCHIVE)).toHaveLength(1);
  });

  it('«Отмена» закрывает окно и ничего не отправляет', async () => {
    const user = userEvent.setup();
    const { calls } = await openArchiveDialog({});

    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: t.common.cancel }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(callsTo(calls, ARCHIVE)).toHaveLength(0);
  });

  it('архивный счёт архивировать и ставить на паузу больше нечем', async () => {
    installFetchMock(withAccounts([account({ status: 'archived' })]));
    renderApp(['/accounts?archived=1']);

    expect(await screen.findByText(t.accounts.statusArchived)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.accounts.archive })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: t.accounts.pause })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.accounts.delete })).toBeInTheDocument();
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

  async function fillCreateForm(
    createRoute: MockRoute = () =>
      jsonResponse(201, account({ label: 'Новый', status: 'pending' })),
  ): Promise<{ calls: MockedCall[]; client: QueryClient }> {
    const user = userEvent.setup();
    const { calls } = installFetchMock(withAccounts([], { [CREATE]: createRoute }));
    const { client } = await openAccounts();

    await user.click(screen.getByRole('button', { name: t.accounts.add }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(t.accounts.labelLabel), 'Новый');
    await user.type(within(dialog).getByLabelText(t.accounts.serverLabel), 'FTMO-Demo');
    await user.type(within(dialog).getByLabelText(t.accounts.loginLabel), '5001234');
    await user.type(within(dialog).getByLabelText(t.accounts.passwordLabel), PASSWORD);
    return { calls, client };
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
   * Acceptance тикета: пароль не должен пережить сохранение. Проверяется по всем местам
   * сразу (`findSecret`), а не по разметке: значение поля живёт в свойстве `value`, а тело
   * запроса — в кэше мутаций, и «нет в `innerHTML`» не говорит ни о том, ни о другом.
   */
  it('после сохранения пароля нет ни в поле, ни в разметке, ни в кэше мутаций', async () => {
    const user = userEvent.setup();
    const { calls, client } = await fillCreateForm();

    // До отправки пароль в поле есть — иначе проверка после отправки ничего не значит.
    expect(findSecret(PASSWORD, client)).toContain('значение поля account-create-password');

    await user.click(screen.getByRole('button', { name: t.accounts.create }));

    await waitFor(() => {
      expect(callsTo(calls, CREATE)).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(findSecret(PASSWORD, client)).toEqual([]);
    // Мутация стирается целиком, а не ждёт сборщика мусора пять минут.
    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });

  /**
   * Второй путь к тому же телу запроса. Отказ сервера до `onSuccess` не доходит, поэтому
   * пароль остаётся в кэше мутаций — и остался бы там на пять минут `gcTime`, если человек
   * просто закрыл окно, не повторив попытку.
   */
  it('после отказа и закрытия формы пароля нет в кэше мутаций', async () => {
    const user = userEvent.setup();
    const { calls, client } = await fillCreateForm(() =>
      errorResponse(409, 'account_already_exists', 'уже есть'),
    );

    await user.click(screen.getByRole('button', { name: t.accounts.create }));

    await waitFor(() => {
      expect(callsTo(calls, CREATE)).toHaveLength(1);
    });
    // Пока форма на экране, человек обязан видеть, что случилось: стирание тела запроса
    // не имеет права гасить текст ошибки.
    expect(await screen.findByText(new RegExp(t.accounts.createFailed))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(t.errors.accountAlreadyExists))).toBeInTheDocument();
    // И тело запроса на этот момент ещё в кэше — иначе проверка после закрытия пуста.
    expect(findSecret(PASSWORD, client)).toContain('кэш мутаций');

    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: t.common.cancel }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(findSecret(PASSWORD, client)).toEqual([]);
    expect(client.getMutationCache().getAll()).toHaveLength(0);
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
