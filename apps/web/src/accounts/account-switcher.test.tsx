/**
 * Переключатель счетов целиком (SPEC.md 9.2): пресеты, предупреждение «демо и реал
 * вместе» и заведение счёта из шапки (`S2-11`).
 *
 * Раскладку эти тесты не проверяют — в jsdom стилей нет, — поэтому текст, спрятанный до
 * `sm`, здесь виден. Проверяется то, от чего зависит смысл: когда элемент есть в
 * документе, а когда его нет вовсе.
 *
 * Экран под шапкой — календарь: он дешевле журнала и дашборда и об одном запросе.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Account } from '@/accounts/api';
import { useAccountSelectionStore } from '@/accounts/selection';
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

const SESSION = 'GET /api/v1/auth/me';
const ACCOUNTS = 'GET /api/v1/accounts';
const CALENDAR = 'GET /api/v1/journal/calendar';
const CREATE = 'POST /api/v1/accounts';

const DEMO_ONE = '0199a2b0-0000-7000-8000-0000000000d1';
const DEMO_TWO = '0199a2b0-0000-7000-8000-0000000000d2';
const REAL_ONE = '0199a2b0-0000-7000-8000-0000000000r1';
const REAL_TWO = '0199a2b0-0000-7000-8000-0000000000r2';
const CREATED_ID = '0199a2b0-0000-7000-8000-0000000000ff';

function account(overrides: Partial<Account> = {}): Account {
  return {
    id: DEMO_ONE,
    label: 'Демо: скальпинг',
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

/** Четыре демо-счёта — установка первого пользователя (тикет `S2-11`). */
const ALL_DEMO: Account[] = [
  account(),
  account({ id: DEMO_TWO, label: 'Демо: свинг' }),
  account({ id: '0199a2b0-0000-7000-8000-0000000000d3', label: 'Демо: новости' }),
  account({ id: '0199a2b0-0000-7000-8000-0000000000d4', label: 'Демо: песочница' }),
];

const MIXED: Account[] = [account(), account({ id: REAL_ONE, label: 'Реал', is_demo: false })];

const ALL_REAL: Account[] = [
  account({ id: REAL_ONE, label: 'Реал', is_demo: false }),
  account({ id: DEMO_TWO, label: 'Второй реал', is_demo: false }),
];

/** Два реальных счёта нужны, чтобы «Все реальные» разворачивался больше чем в один. */
const TWO_REAL_ONE_DEMO: Account[] = [
  account({ id: REAL_ONE, label: 'Реал: первый', is_demo: false }),
  account({ id: REAL_TWO, label: 'Реал: второй', is_demo: false }),
  account(),
];

function routes(items: Account[], extra: RouteTable = {}): RouteTable {
  return {
    [SESSION]: () => jsonResponse(200, TEST_USER),
    [ACCOUNTS]: () => jsonResponse(200, { items }),
    [CALENDAR]: ({ url }) =>
      jsonResponse(200, {
        month: url.searchParams.get('month') ?? '2026-09',
        timezone: TEST_USER.timezone,
        day_boundary_hour: 0,
        days: [],
      }),
    ...extra,
  };
}

function trigger(): HTMLElement {
  return screen.getByRole('button', { name: t.accountSwitcher.open });
}

async function openSwitcher(
  user: ReturnType<typeof userEvent.setup>,
  name: string = t.accountSwitcher.open,
): Promise<HTMLElement> {
  const button = await screen.findByRole('button', { name });
  await user.click(button);
  const id = button.getAttribute('aria-controls');
  if (id === null) {
    throw new Error('Список счетов не открылся: у кнопки нет aria-controls');
  }
  const list = document.getElementById(id);
  if (list === null) {
    throw new Error(`Списка ${id} нет в документе`);
  }
  return list;
}

async function openCalendar(items: Account[], extra: RouteTable = {}): Promise<MockedCall[]> {
  const { calls } = installFetchMock(routes(items, extra));
  renderApp(['/calendar']);
  await screen.findByRole('heading', { name: t.pages.calendar });
  return calls;
}

beforeEach(() => {
  window.localStorage.clear();
  useAccountSelectionStore.setState({ mode: 'all', ids: [] });
});

describe('пресеты выбора', () => {
  it('«Все реальные» показан, когда счета обоих видов: только там у пресета есть смысл', async () => {
    const user = userEvent.setup();
    await openCalendar(MIXED);

    // Смешанный выбор переименовывает кнопку: она и есть предупреждение для незрячего.
    const list = await openSwitcher(user, t.accountSwitcher.openMixed);

    expect(within(list).getByRole('button', { name: t.accountSwitcher.all })).toBeInTheDocument();
    expect(
      within(list).getByRole('button', { name: t.accountSwitcher.allReal }),
    ).toBeInTheDocument();
  });

  /** Установка первого пользователя: пресет дал бы пустой экран по нажатию. */
  it('при одних демо-счетах «Все реальные» не показывается вовсе', async () => {
    const user = userEvent.setup();
    await openCalendar(ALL_DEMO);

    const list = await openSwitcher(user);

    expect(within(list).getByRole('button', { name: t.accountSwitcher.all })).toBeInTheDocument();
    expect(
      within(list).queryByRole('button', { name: t.accountSwitcher.allReal }),
    ).not.toBeInTheDocument();
  });

  it('без единого демо-счёта «Все реальные» равен «Все» и тоже не показывается', async () => {
    const user = userEvent.setup();
    await openCalendar(ALL_REAL);

    const list = await openSwitcher(user);

    expect(
      within(list).queryByRole('button', { name: t.accountSwitcher.allReal }),
    ).not.toBeInTheDocument();
  });

  /**
   * Режим переживает архивацию последнего реального счёта и приезжает из другой вкладки.
   * Спрятанный под ним пресет оставил бы человека с пустым журналом и без способа
   * увидеть, чем тот пуст.
   */
  it('уже выбранный «Все реальные» показан даже там, где реальных счетов нет', async () => {
    useAccountSelectionStore.setState({ mode: 'all_real', ids: [] });
    const user = userEvent.setup();
    await openCalendar(ALL_DEMO);

    const list = await openSwitcher(user);
    const preset = within(list).getByRole('button', { name: t.accountSwitcher.allReal });

    expect(preset).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(t.calendar.emptyRealAccounts)).toBeInTheDocument();
  });

  it('нажатие пресета уходит в account_ids и перезапрашивает экран без перезагрузки', async () => {
    const user = userEvent.setup();
    const calls = await openCalendar(MIXED);

    await waitFor(() => {
      expect(calls.filter((call) => call.path === '/api/v1/journal/calendar')).not.toHaveLength(0);
    });
    const before = calls.filter((call) => call.path === '/api/v1/journal/calendar').length;

    const list = await openSwitcher(user, t.accountSwitcher.openMixed);
    await user.click(within(list).getByRole('button', { name: t.accountSwitcher.allReal }));

    await waitFor(() => {
      expect(
        calls.filter((call) => call.path === '/api/v1/journal/calendar').length,
      ).toBeGreaterThan(before);
    });
    expect(useAccountSelectionStore.getState().mode).toBe('all_real');
    // Кнопка называет правило, а не единственный подошедший под него счёт.
    expect(screen.getByRole('button', { name: t.accountSwitcher.open })).toHaveTextContent(
      t.accountSwitcher.allReal,
    );
  });

  /**
   * Инвариант: нарисованное состояние галочки и результат щелчка по ней совпадают.
   *
   * Пресет рисует галочки на счетах, которые под него подошли, поэтому щелчок обязан
   * вычитать счёт из этого набора. Пока основа щелчка считалась «пустой», снятая галочка
   * оставалась отмеченной, а соседние реальные счета молча уходили из выборки.
   */
  it('снятая галочка при «Всех реальных» вычитает счёт, а соседний остаётся в выборке', async () => {
    useAccountSelectionStore.setState({ mode: 'all_real', ids: [] });
    const user = userEvent.setup();
    await openCalendar(TWO_REAL_ONE_DEMO);

    const list = await openSwitcher(user);
    const first = within(list).getByRole('checkbox', { name: /Реал: первый/ });
    const second = within(list).getByRole('checkbox', { name: /Реал: второй/ });
    expect(first).toBeChecked();
    expect(second).toBeChecked();

    await user.click(first);

    expect(first).not.toBeChecked();
    expect(second).toBeChecked();
    expect(useAccountSelectionStore.getState()).toMatchObject({
      mode: 'single',
      ids: [REAL_TWO],
    });
  });

  it('галочка на демо-счёте поверх «Всех реальных» добавляется к ним, а не заменяет их', async () => {
    useAccountSelectionStore.setState({ mode: 'all_real', ids: [] });
    const user = userEvent.setup();
    await openCalendar(TWO_REAL_ONE_DEMO);

    const list = await openSwitcher(user);
    await user.click(within(list).getByRole('checkbox', { name: /Демо: скальпинг/ }));

    expect(useAccountSelectionStore.getState()).toMatchObject({
      mode: 'multi',
      ids: [REAL_ONE, REAL_TWO, DEMO_ONE],
    });
    // Демо к реалам — это ровно то смешение, о котором предупреждают.
    expect(await screen.findByText(t.accountSwitcher.mixedBadge)).toBeInTheDocument();
  });

  it('«Все счета» возвращает выбор к полному и снимает галочки', async () => {
    useAccountSelectionStore.setState({ mode: 'single', ids: [REAL_ONE] });
    const user = userEvent.setup();
    await openCalendar(MIXED);

    const list = await openSwitcher(user);
    expect(within(list).getByRole('checkbox', { name: /Реал/ })).toBeChecked();

    await user.click(within(list).getByRole('button', { name: t.accountSwitcher.all }));

    expect(useAccountSelectionStore.getState().mode).toBe('all');
    expect(within(list).getByRole('checkbox', { name: /Реал/ })).not.toBeChecked();
  });
});

describe('список на узком экране', () => {
  /**
   * `matchMedia` в jsdom нет вовсе, поэтому ширина подменяется явно: без подмены экран
   * считается широким, а там список висит на кнопке и едет вместе с ней.
   */
  function pretendNarrow(): void {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
  }

  it('прокрутка страницы закрывает список: он приколот к окну, а шапка едет вместе с ней', async () => {
    pretendNarrow();
    const user = userEvent.setup();
    await openCalendar(ALL_DEMO);

    const list = await openSwitcher(user);
    fireEvent.scroll(window);

    await waitFor(() => {
      expect(list).not.toBeInTheDocument();
    });
  });

  it('на широком экране прокрутка список не закрывает: он висит на кнопке', async () => {
    const user = userEvent.setup();
    await openCalendar(ALL_DEMO);

    const list = await openSwitcher(user);
    fireEvent.scroll(window);

    expect(list).toBeInTheDocument();
  });
});

describe('предупреждение «демо и реал вместе»', () => {
  it('при пресете «Все» и счетах обоих видов предупреждение видно и в шапке, и в списке', async () => {
    const user = userEvent.setup();
    await openCalendar(MIXED);

    expect(await screen.findByText(t.accountSwitcher.mixedBadge)).toBeInTheDocument();
    // Кнопка переключателя называет предупреждение сама: значок рядом с ней для
    // незрячего человека не существует.
    expect(screen.getByRole('button', { name: t.accountSwitcher.openMixed })).toBeInTheDocument();

    const list = await openSwitcher(user, t.accountSwitcher.openMixed);
    expect(within(list).getByText(t.accountSwitcher.mixedNote)).toBeInTheDocument();
  });

  it('при одних демо-счетах «Все» ничего не смешивает и предупреждения нет', async () => {
    await openCalendar(ALL_DEMO);

    expect(await screen.findByRole('button', { name: t.accountSwitcher.open })).toBeInTheDocument();
    expect(screen.queryByText(t.accountSwitcher.mixedBadge)).not.toBeInTheDocument();
  });

  it('один выбранный счёт из смешанного списка предупреждения не даёт', async () => {
    useAccountSelectionStore.setState({ mode: 'single', ids: [DEMO_ONE] });
    await openCalendar(MIXED);

    expect(await screen.findByRole('button', { name: t.accountSwitcher.open })).toBeInTheDocument();
    expect(screen.queryByText(t.accountSwitcher.mixedBadge)).not.toBeInTheDocument();
  });

  it('предупреждение считается по составу выборки, а не по имени пресета', async () => {
    // Смешать демо и реал галочками так же легко, как пресетом «Все», и сумма выйдет та же.
    useAccountSelectionStore.setState({ mode: 'multi', ids: [DEMO_ONE, REAL_ONE] });
    await openCalendar(MIXED);

    expect(await screen.findByText(t.accountSwitcher.mixedBadge)).toBeInTheDocument();
  });

  it('пресет «Все реальные» демо не тянет и предупреждения не даёт', async () => {
    useAccountSelectionStore.setState({ mode: 'all_real', ids: [] });
    await openCalendar(MIXED);

    expect(await screen.findByRole('button', { name: t.accountSwitcher.open })).toBeInTheDocument();
    expect(screen.queryByText(t.accountSwitcher.mixedBadge)).not.toBeInTheDocument();
  });
});

describe('заведение счёта из шапки', () => {
  const created = account({
    id: CREATED_ID,
    label: 'Демо: пятый',
    status: 'pending',
    platform: 'mt5',
  });

  async function fillForm(
    user: ReturnType<typeof userEvent.setup>,
    createRoute: MockRoute = () => jsonResponse(201, created),
    items: Account[] = ALL_DEMO,
  ): Promise<MockedCall[]> {
    const calls = await openCalendar(items, { [CREATE]: createRoute });
    const list = await openSwitcher(user);
    await user.click(within(list).getByRole('button', { name: t.accountSwitcher.add }));

    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(t.accounts.labelLabel), 'Демо: пятый');
    await user.type(within(dialog).getByLabelText(t.accounts.serverLabel), 'Broker-Demo');
    await user.type(within(dialog).getByLabelText(t.accounts.loginLabel), '5001234');
    return calls;
  }

  it('кнопка в списке открывает ту же форму — и она тоже не спрашивает пароль', async () => {
    const user = userEvent.setup();
    await openCalendar(ALL_DEMO);

    const list = await openSwitcher(user);
    await user.click(within(list).getByRole('button', { name: t.accountSwitcher.add }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText(t.accounts.serverLabel)).toBeInTheDocument();
    // `T-07`: форма одна на два экрана, и второй вход в неё обязан быть таким же.
    expect(within(dialog).getByText(t.accounts.loginHint)).toBeInTheDocument();
    expect(dialog.querySelector('input[type="password"]')).toBeNull();
    // Список закрывается за собой: иначе он остаётся под окном и всплывает после него.
    expect(list).not.toBeInTheDocument();
  });

  /** Acceptance тикета: человек понимает, что произошло и где смотреть дальше. */
  it('после создания окно объясняет, что случилось, и предлагает открыть счёт', async () => {
    const user = userEvent.setup();
    const calls = await fillForm(user);

    await user.click(screen.getByRole('button', { name: t.accounts.create }));

    const dialog = await screen.findByRole('dialog');
    expect(
      await within(dialog).findByText(t.accountSwitcher.createdLead('Демо: пятый')),
    ).toBeInTheDocument();
    expect(within(dialog).getByText(t.accountSwitcher.createdMt5)).toBeInTheDocument();
    // Кнопка «Добавить» исчезла вместе с формой: без явного перевода фокус достаётся
    // `body`, и сказанное здесь экранный диктор не читает вовсе.
    expect(
      within(dialog).getByText(t.accountSwitcher.createdLead('Демо: пятый')).parentElement,
    ).toHaveFocus();
    expect(
      within(dialog).getByRole('link', { name: t.accountSwitcher.createdOpen }),
    ).toHaveAttribute('href', `/accounts/${CREATED_ID}`);
    expect(calls.filter((call) => `${call.method} ${call.path}` === CREATE)).toHaveLength(1);
  });

  it('при выборе «все счета» новый счёт уже в выборке, и переставлять нечего', async () => {
    const user = userEvent.setup();
    await fillForm(user);

    await user.click(screen.getByRole('button', { name: t.accounts.create }));

    const dialog = await screen.findByRole('dialog');
    expect(
      await within(dialog).findByText(t.accountSwitcher.createdInSelection),
    ).toBeInTheDocument();
    expect(
      within(dialog).queryByRole('button', { name: t.accountSwitcher.createdSelectIt }),
    ).not.toBeInTheDocument();
  });

  /**
   * Сценарий первого пользователя: он смотрит счета по одному. Новый счёт в его выборку
   * не входит, и молча переставить выбор нельзя — это его настройка рабочего места.
   */
  it('при выборе одного счёта новый в выборку не попадает, и это сказано, а не сделано молча', async () => {
    useAccountSelectionStore.setState({ mode: 'single', ids: [DEMO_ONE] });
    const user = userEvent.setup();
    await fillForm(user);

    await user.click(screen.getByRole('button', { name: t.accounts.create }));

    const dialog = await screen.findByRole('dialog');
    expect(
      await within(dialog).findByText(t.accountSwitcher.createdOutOfSelection),
    ).toBeInTheDocument();
    // Выбор не изменился сам.
    expect(useAccountSelectionStore.getState()).toMatchObject({ mode: 'single', ids: [DEMO_ONE] });

    await user.click(
      within(dialog).getByRole('button', { name: t.accountSwitcher.createdSelectIt }),
    );

    expect(useAccountSelectionStore.getState()).toMatchObject({
      mode: 'single',
      ids: [CREATED_ID],
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  /**
   * Тело запроса не остаётся в кэше мутаций: окно после успеха с экрана не уходит, а
   * `variables` жили бы там до сборщика мусора. Секрета в теле с `T-07` больше нет — здесь
   * проверяется сам механизм, потому что на нём же держится признак «сохранено».
   */
  it('после создания тело запроса не остаётся в кэше мутаций', async () => {
    const user = userEvent.setup();
    installFetchMock(routes(ALL_DEMO, { [CREATE]: () => jsonResponse(201, created) }));
    const { client } = renderApp(['/calendar']);
    await screen.findByRole('heading', { name: t.pages.calendar });

    const list = await openSwitcher(user);
    await user.click(within(list).getByRole('button', { name: t.accountSwitcher.add }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(t.accounts.labelLabel), 'Демо: пятый');
    await user.type(within(dialog).getByLabelText(t.accounts.serverLabel), 'Broker-Demo');
    await user.type(within(dialog).getByLabelText(t.accounts.loginLabel), '5001234');

    await user.click(screen.getByRole('button', { name: t.accounts.create }));
    await screen.findByText(t.accountSwitcher.createdLead('Демо: пятый'));

    expect(client.getMutationCache().getAll()).toHaveLength(0);
  });

  it('серверная ошибка показана, форма остаётся с введённым', async () => {
    const user = userEvent.setup();
    await fillForm(user, () => errorResponse(409, 'account_already_exists', 'уже есть'));

    await user.click(screen.getByRole('button', { name: t.accounts.create }));

    expect(await screen.findByText(new RegExp(t.accounts.createFailed))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(t.errors.accountAlreadyExists))).toBeInTheDocument();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText(t.accounts.labelLabel)).toHaveValue('Демо: пятый');
  });

  it('«Отмена» закрывает окно и ничего не отправляет', async () => {
    const user = userEvent.setup();
    const calls = await fillForm(user);

    await user.click(screen.getByRole('button', { name: t.common.cancel }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(calls.filter((call) => `${call.method} ${call.path}` === CREATE)).toHaveLength(0);
  });

  /** Заголовок окна — единственное, что остаётся на месте формы: он обязан смениться. */
  it('после создания окно называется «Счёт добавлен», а не «Добавить счёт»', async () => {
    const user = userEvent.setup();
    await fillForm(user);

    expect(screen.getByRole('dialog')).toHaveAccessibleName(t.accounts.formCreateTitle);

    await user.click(screen.getByRole('button', { name: t.accounts.create }));

    await screen.findByText(t.accountSwitcher.createdLead('Демо: пятый'));
    expect(screen.getByRole('dialog')).toHaveAccessibleName(t.accountSwitcher.createdTitle);
  });

  /**
   * Счёт «вручную» коллектор не ведёт, и обещать ему первый синк нельзя: сделки к нему
   * добавляет человек, и ждать их появления бессмысленно.
   */
  it('у счёта «вручную» окно говорит про ручное добавление сделок, а не про коллектор', async () => {
    const user = userEvent.setup();
    const manual = account({
      id: CREATED_ID,
      label: 'Ручной',
      platform: 'manual',
      server: null,
      login: null,
    });
    await openCalendar(ALL_DEMO, { [CREATE]: () => jsonResponse(201, manual) });

    const list = await openSwitcher(user);
    await user.click(within(list).getByRole('button', { name: t.accountSwitcher.add }));
    const dialog = await screen.findByRole('dialog');
    await user.selectOptions(within(dialog).getByLabelText(t.accounts.platformLabel), 'manual');
    await user.type(within(dialog).getByLabelText(t.accounts.labelLabel), 'Ручной');

    // Полей MT5 у такого счёта нет вовсе — коллектор в него не ходит.
    expect(within(dialog).queryByLabelText(t.accounts.serverLabel)).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText(t.accounts.loginLabel)).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: t.accounts.create }));

    expect(await within(dialog).findByText(t.accountSwitcher.createdManual)).toBeInTheDocument();
    expect(within(dialog).queryByText(t.accountSwitcher.createdMt5)).not.toBeInTheDocument();
  });

  /**
   * Два счёта из одного нажатия — это два счёта у брокера в работе коллектора. Защиты
   * здесь две, и мимо одной проходит то, что ловит другая: атрибут `disabled` держит
   * второй щелчок, а проверка в обработчике — отправку формы, которая до кнопки не
   * доходит (Enter в поле, второй щелчок до перерисовки).
   */
  it('пока запрос идёт, повторная отправка второго счёта не создаёт', async () => {
    const user = userEvent.setup();
    let release = (): void => {};
    const answered = new Promise<void>((resolve) => {
      release = resolve;
    });
    const calls = await fillForm(user, async () => {
      await answered;
      return jsonResponse(201, created);
    });

    await user.click(screen.getByRole('button', { name: t.accounts.create }));

    const pending = await screen.findByRole('button', { name: t.accounts.creating });
    expect(pending).toBeDisabled();
    // «Отмена» на время запроса тоже заперта: она увела бы окно из-под ответа сервера.
    expect(screen.getByRole('button', { name: t.common.cancel })).toBeDisabled();

    await user.click(pending);
    const form = pending.closest('form');
    if (form === null) {
      throw new Error('Форма счёта не найдена');
    }
    fireEvent.submit(form);

    release();
    await screen.findByText(t.accountSwitcher.createdLead('Демо: пятый'));
    expect(calls.filter((call) => `${call.method} ${call.path}` === CREATE)).toHaveLength(1);
  });

  /**
   * Кнопка, открывшая окно, уезжает из документа вместе со списком. Без явного перевода
   * фокуса заранее окно возвращает его `body`, и клавиатура начинает обход страницы
   * заново — то же, что чинили X-16 и X-36.
   */
  it('закрытое окно возвращает фокус на кнопку переключателя', async () => {
    const user = userEvent.setup();
    await openCalendar(ALL_DEMO);

    const list = await openSwitcher(user);
    await user.click(within(list).getByRole('button', { name: t.accountSwitcher.add }));
    await screen.findByRole('dialog');

    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(trigger()).toHaveFocus();
  });
});
