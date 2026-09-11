import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { t } from '@/i18n';
import { isKnownTimeZone } from '@/lib/time-zones';
import {
  errorResponse,
  installFetchMock,
  jsonResponse,
  type MockedCall,
  type RouteTable,
} from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';

const SESSION = 'GET /api/v1/auth/me';
const PROFILE = 'GET /api/v1/users/me';
const SAVE = 'PATCH /api/v1/users/me';
const TIME_ZONES = 'GET /api/v1/users/timezones';

/**
 * Ответ `GET /users/timezones`. Нарочно короткий и нарочно не совпадает с набором
 * движка: меню обязано показывать ровно эти имена. Именно расхождение наборов и было
 * дефектом — часть имён из `Intl` сервер отвергает `400`.
 */
const SERVER_TIME_ZONES = [
  'America/New_York',
  'Asia/Kolkata',
  'Asia/Tokyo',
  'Asia/Yekaterinburg',
  'Europe/Moscow',
];

/** Имя, которое движок знает, а сервер не прислал: в меню ему не место. */
const NOT_OFFERED = 'Europe/Berlin';

/** Профиль тестового пользователя: Asia/Yekaterinburg (UTC+5), день с полуночи. */
const authorized: RouteTable = {
  [SESSION]: () => jsonResponse(200, TEST_USER),
  [PROFILE]: () => jsonResponse(200, TEST_USER),
  [TIME_ZONES]: () => jsonResponse(200, { items: SERVER_TIME_ZONES }),
};

function optionValues(select: HTMLSelectElement): string[] {
  return [...select.options].map((option) => option.value);
}

async function openSettings(): Promise<HTMLSelectElement> {
  renderApp(['/settings']);
  return (await screen.findByLabelText(t.settings.timezoneLabel)) as HTMLSelectElement;
}

/** Экран с уже пришедшим списком зон: до его прихода поле зоны заблокировано. */
async function openSettingsWithZones(): Promise<HTMLSelectElement> {
  const timezone = await openSettings();
  await waitFor(() => {
    expect(timezone).toBeEnabled();
  });
  return timezone;
}

function nameField(): HTMLInputElement {
  return screen.getByLabelText(t.settings.displayNameLabel) as HTMLInputElement;
}

function saveButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: t.settings.save }) as HTMLButtonElement;
}

/** Запросы одного маршрута; ключ — тот же, что в таблице моков. */
function callsTo(calls: MockedCall[], route: string): MockedCall[] {
  return calls.filter((call) => `${call.method} ${call.path}` === route);
}

/** Список зон упал один раз, со второй попытки приходит. */
function flakyTimeZones(): RouteTable {
  let attempt = 0;
  return {
    ...authorized,
    [SAVE]: () => jsonResponse(200, { ...TEST_USER, display_name: 'Ник' }),
    [TIME_ZONES]: () => {
      attempt += 1;
      return attempt === 1
        ? errorResponse(500, 'internal_error', 'Внутренняя ошибка')
        : jsonResponse(200, { items: SERVER_TIME_ZONES });
    },
  };
}

afterEach(() => {
  vi.useRealTimers();
});

describe('/settings', () => {
  it('показывает сохранённые значения профиля', async () => {
    installFetchMock(authorized);
    await openSettingsWithZones();

    expect(screen.getByLabelText(t.settings.emailLabel)).toHaveValue(TEST_USER.email);
    expect(screen.getByLabelText(t.settings.timezoneLabel)).toHaveValue(TEST_USER.timezone);
    expect(screen.getByLabelText(t.settings.dayBoundaryLabel)).toHaveValue(
      String(TEST_USER.day_boundary_hour),
    );
    expect(nameField()).toHaveValue('');
    // Пока ничего не изменено, сохранять нечего: пустой PATCH — лишний запрос.
    expect(saveButton()).toBeDisabled();
  });

  it('смена таймзоны меняет пример времени сразу, до сохранения', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(new Date('2026-09-05T18:34:00Z'));
    const { calls } = installFetchMock(authorized);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    const timezone = await openSettingsWithZones();
    expect(screen.getByText(t.settings.previewNow('05.09.2026 23:34'))).toBeInTheDocument();

    await user.selectOptions(timezone, 'Europe/Moscow');

    expect(screen.getByText(t.settings.previewNow('05.09.2026 21:34'))).toBeInTheDocument();
    expect(calls.some((call) => call.method === 'PATCH')).toBe(false);
  });

  it('начало торгового дня меняет текущий торговый день в примере', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    // 06:34 утра по Екатеринбургу: до границы в 9 часов, но уже после полуночи.
    vi.setSystemTime(new Date('2026-09-05T01:34:00Z'));
    installFetchMock(authorized);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await openSettings();
    expect(
      screen.getByText(t.settings.previewTradingDay('05.09.2026', '00:00')),
    ).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(t.settings.dayBoundaryLabel), '9');

    // Утро до границы принадлежит вчерашнему торговому дню — это и есть смысл поля.
    expect(
      screen.getByText(t.settings.previewTradingDay('04.09.2026', '09:00')),
    ).toBeInTheDocument();
  });

  it('сохраняет только изменённые поля и блокирует форму на время запроса', async () => {
    // Ответ придерживается до проверки: состояние «сохраняем» иначе не увидеть.
    let release = (): void => {};
    const gate = new Promise<void>((resolve) => {
      release = () => resolve();
    });
    const { calls } = installFetchMock({
      ...authorized,
      [SAVE]: async () => {
        await gate;
        return jsonResponse(200, {
          ...TEST_USER,
          display_name: 'Ник',
          timezone: 'Europe/Moscow',
        });
      },
    });
    const user = userEvent.setup();

    const timezone = await openSettingsWithZones();
    await user.type(nameField(), '  Ник  ');
    await user.selectOptions(timezone, 'Europe/Moscow');
    await user.click(saveButton());

    const saving = await screen.findByRole('button', { name: t.settings.saving });
    expect(saving).toBeDisabled();

    release();

    expect(await screen.findByText(t.settings.saved)).toBeInTheDocument();
    const patch = calls.find((call) => call.method === 'PATCH');
    // Час начала дня не менялся — его в теле быть не должно: отсутствие поля
    // означает «не трогать», а присланное значение перезаписывает.
    expect(patch?.body).toEqual({ display_name: 'Ник', timezone: 'Europe/Moscow' });
    expect(saveButton()).toBeDisabled();
  });

  it('пустое имя очищает его: в теле null, а не пустая строка', async () => {
    const named = { ...TEST_USER, display_name: 'Ник' };
    const { calls } = installFetchMock({
      ...authorized,
      [SESSION]: () => jsonResponse(200, named),
      [PROFILE]: () => jsonResponse(200, named),
      [SAVE]: () => jsonResponse(200, { ...named, display_name: null }),
    });
    const user = userEvent.setup();

    await openSettings();
    await user.clear(nameField());
    await user.click(saveButton());

    await screen.findByText(t.settings.saved);
    expect(calls.find((call) => call.method === 'PATCH')?.body).toEqual({ display_name: null });
  });

  it('validation_error показывает текст сервера у поля и не теряет введённое', async () => {
    const message = 'Неизвестная таймзона. Ожидается имя IANA, например Europe/Moscow';
    installFetchMock({
      ...authorized,
      [SAVE]: () =>
        errorResponse(400, 'validation_error', 'Проверьте поля', {
          fields: { 'body.timezone': message },
        }),
    });
    const user = userEvent.setup();

    const timezone = await openSettingsWithZones();
    await user.type(nameField(), 'Ник');
    await user.selectOptions(timezone, 'Europe/Moscow');
    await user.click(saveButton());

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByLabelText(t.settings.timezoneLabel)).toHaveAttribute('aria-invalid', 'true');
    // Введённое остаётся на месте: переписывать всё заново из-за ошибки нельзя.
    expect(nameField()).toHaveValue('Ник');
    expect(screen.getByLabelText(t.settings.timezoneLabel)).toHaveValue('Europe/Moscow');
  });

  it('оборванная сеть объясняется человеку, значения формы остаются', async () => {
    installFetchMock({
      ...authorized,
      [SAVE]: () => {
        throw new TypeError('Failed to fetch');
      },
    });
    const user = userEvent.setup();

    await openSettings();
    await user.type(nameField(), 'Ник');
    await user.click(saveButton());

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(t.settings.saveFailed);
    expect(alert).toHaveTextContent(t.errors.serverDown);
    expect(nameField()).toHaveValue('Ник');
  });

  it('401 при сохранении уводит на вход', async () => {
    installFetchMock({
      ...authorized,
      [SAVE]: () => errorResponse(401, 'unauthorized', 'Требуется вход'),
    });
    const user = userEvent.setup();

    await openSettings();
    await user.type(nameField(), 'Ник');
    await user.click(saveButton());

    expect(await screen.findByRole('heading', { name: t.login.title })).toBeInTheDocument();
  });

  it('«Отмена» возвращает сохранённые значения и ничего не отправляет', async () => {
    const { calls } = installFetchMock(authorized);
    const user = userEvent.setup();

    const timezone = await openSettingsWithZones();
    await user.type(nameField(), 'Ник');
    await user.selectOptions(timezone, 'Europe/Moscow');

    await user.click(screen.getByRole('button', { name: t.settings.cancel }));

    expect(nameField()).toHaveValue('');
    expect(screen.getByLabelText(t.settings.timezoneLabel)).toHaveValue(TEST_USER.timezone);
    expect(saveButton()).toBeDisabled();
    expect(calls.some((call) => call.method === 'PATCH')).toBe(false);
  });

  it('ошибка загрузки профиля показывается, «Повторить» перечитывает', async () => {
    let attempt = 0;
    installFetchMock({
      ...authorized,
      [PROFILE]: () => {
        attempt += 1;
        return attempt === 1
          ? errorResponse(500, 'internal_error', 'Внутренняя ошибка')
          : jsonResponse(200, TEST_USER);
      },
    });
    const user = userEvent.setup();
    renderApp(['/settings']);

    expect(await screen.findByRole('alert')).toHaveTextContent(t.settings.loadFailed);

    await user.click(screen.getByRole('button', { name: t.common.retry }));

    expect(await screen.findByLabelText(t.settings.timezoneLabel)).toHaveValue(TEST_USER.timezone);
  });

  it('поиск сужает список зон и не выбрасывает из него выбранную', async () => {
    installFetchMock(authorized);
    const user = userEvent.setup();

    const timezone = await openSettingsWithZones();
    await user.type(screen.getByLabelText(t.settings.timezoneSearchLabel), 'new york');

    await waitFor(() => {
      expect(timezone.options.length).toBe(2);
    });
    expect([...timezone.options].map((option) => option.value)).toEqual([
      TEST_USER.timezone,
      'America/New_York',
    ]);
    expect(timezone).toHaveValue(TEST_USER.timezone);
  });

  it('пустой результат поиска объясняется, а не выглядит поломкой', async () => {
    installFetchMock(authorized);
    const user = userEvent.setup();

    await openSettingsWithZones();
    await user.type(screen.getByLabelText(t.settings.timezoneSearchLabel), 'такой зоны нет');

    expect(await screen.findByText(t.settings.timezoneSearchEmpty)).toBeInTheDocument();
  });

  it('незнакомая движку зона предупреждает, но не роняет экран', async () => {
    // Наборы имён IANA у браузера и у сервера расходятся по псевдонимам. Имя взято
    // заведомо несуществующее: любое настоящее знает то один движок, то другой.
    const alien = { ...TEST_USER, timezone: 'Mars/Olympus' };
    installFetchMock({
      ...authorized,
      [SESSION]: () => jsonResponse(200, alien),
      [PROFILE]: () => jsonResponse(200, alien),
    });

    const timezone = await openSettingsWithZones();

    expect(screen.getByText(t.settings.timezoneUnknown('Mars/Olympus'))).toBeInTheDocument();
    // Сохранённое значение остаётся выбранным: подменять его на похожее нельзя.
    expect(timezone).toHaveValue('Mars/Olympus');
    // Время всё равно показано — по часам компьютера.
    expect(
      screen.getByText(new RegExp(`^${t.settings.previewNow('')}\\d{2}\\.\\d{2}\\.\\d{4}`)),
    ).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
  });

  it('меню строится из ответа сервера, а не из набора движка', async () => {
    installFetchMock(authorized);

    const timezone = await openSettingsWithZones();

    // Ровно присланные имена и ничего сверх. Список движка на порядок длиннее, так что
    // подмена источника обратно на `Intl` этот тест не переживёт.
    expect(optionValues(timezone)).toEqual(
      [...SERVER_TIME_ZONES].sort((left, right) => left.localeCompare(right, 'en')),
    );
    // Имя, которое движок знает, а сервер не прислал: выбрать его человек не должен —
    // сохранение вернуло бы 400 без выхода, это и был дефект.
    expect(optionValues(timezone)).not.toContain(NOT_OFFERED);
    expect(isKnownTimeZone(NOT_OFFERED)).toBe(true);
  });

  it('пока список зон едет, поле объясняет ожидание и не показывает пустоту', async () => {
    let release = (): void => {};
    const gate = new Promise<void>((resolve) => {
      release = () => resolve();
    });
    installFetchMock({
      ...authorized,
      [TIME_ZONES]: async () => {
        await gate;
        return jsonResponse(200, { items: SERVER_TIME_ZONES });
      },
    });

    const timezone = await openSettings();

    expect(screen.getByText(t.settings.timezoneListLoading)).toBeInTheDocument();
    expect(timezone).toBeDisabled();
    // Пустого меню человек не видит: сохранённая зона на месте и выбрана.
    expect(optionValues(timezone)).toEqual([TEST_USER.timezone]);
    expect(timezone).toHaveValue(TEST_USER.timezone);
    // Остальные поля работают, пока список едет.
    expect(nameField()).toBeEnabled();

    release();

    await waitFor(() => {
      expect(timezone).toBeEnabled();
    });
    expect(screen.queryByText(t.settings.timezoneListLoading)).not.toBeInTheDocument();
  });

  it('сбой списка зон гасит одно поле, остальные настройки остаются рабочими', async () => {
    const { calls } = installFetchMock(flakyTimeZones());
    const user = userEvent.setup();

    const timezone = await openSettings();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(t.settings.timezoneListFailed);
    expect(timezone).toBeDisabled();
    expect(timezone).toHaveValue(TEST_USER.timezone);

    // Экран не сломан: имя и час меняются и уходят в PATCH без списка зон.
    await user.type(nameField(), 'Ник');
    expect(saveButton()).toBeEnabled();

    await user.click(screen.getByRole('button', { name: t.common.retry }));

    await waitFor(() => {
      expect(timezone).toBeEnabled();
    });
    expect(optionValues(timezone).length).toBe(SERVER_TIME_ZONES.length);
    // Введённое во время сбоя не потеряно.
    expect(nameField()).toHaveValue('Ник');
    // «Повторить» перезапрашивает список и только его. Кнопка стоит внутри формы, и без
    // явного type она была бы submit: сохранение профиля, которого человек не просил.
    expect(callsTo(calls, SAVE)).toHaveLength(0);
  });

  it('Enter в поле имени сохраняет профиль, а не жмёт «Повторить»', async () => {
    // Форма отправляется первой submit-кнопкой в разметке. Пока «Повторить» не объявляла
    // type, первой была она — и Enter уходил в перезагрузку списка зон.
    const { calls } = installFetchMock(flakyTimeZones());
    const user = userEvent.setup();

    await openSettings();
    await screen.findByRole('button', { name: t.common.retry });

    await user.type(nameField(), 'Ник{Enter}');

    await waitFor(() => {
      expect(callsTo(calls, SAVE)).toHaveLength(1);
    });
    expect(callsTo(calls, SAVE)[0]?.body).toEqual({ display_name: 'Ник' });
    // Регрессию ловит именно эта строка: с багом форма всё равно отправлялась — «Повторить»
    // была default-кнопкой и сабмитила её сама, — но список зон перезапрашивался лишним разом.
    expect(callsTo(calls, TIME_ZONES)).toHaveLength(1);
  });

  it('сохранённая зона вне ответа сервера остаётся выбранной и не подменяется', async () => {
    // Случай Киева: сервер принимает `Europe/Kyiv`, но в присланном наборе его может
    // не быть — как и у движка. Подменить значение на похожее нельзя: следующее
    // сохранение записало бы человеку чужую зону.
    const kyiv = { ...TEST_USER, timezone: 'Europe/Kyiv' };
    installFetchMock({
      ...authorized,
      [SESSION]: () => jsonResponse(200, kyiv),
      [PROFILE]: () => jsonResponse(200, kyiv),
    });

    const timezone = await openSettingsWithZones();

    expect(optionValues(timezone)).toContain('Europe/Kyiv');
    expect(optionValues(timezone).length).toBe(SERVER_TIME_ZONES.length + 1);
    expect(timezone).toHaveValue('Europe/Kyiv');
    // Ничего не изменилось — значит и подмены не было.
    expect(saveButton()).toBeDisabled();
  });
});
