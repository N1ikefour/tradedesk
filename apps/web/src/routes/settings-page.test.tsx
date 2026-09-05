import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { t } from '@/i18n';
import { errorResponse, installFetchMock, jsonResponse, type RouteTable } from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';

const SESSION = 'GET /api/v1/auth/me';
const PROFILE = 'GET /api/v1/users/me';
const SAVE = 'PATCH /api/v1/users/me';

/** Профиль тестового пользователя: Asia/Yekaterinburg (UTC+5), день с полуночи. */
const authorized: RouteTable = {
  [SESSION]: () => jsonResponse(200, TEST_USER),
  [PROFILE]: () => jsonResponse(200, TEST_USER),
};

async function openSettings(): Promise<HTMLSelectElement> {
  renderApp(['/settings']);
  return (await screen.findByLabelText(t.settings.timezoneLabel)) as HTMLSelectElement;
}

function nameField(): HTMLInputElement {
  return screen.getByLabelText(t.settings.displayNameLabel) as HTMLInputElement;
}

function saveButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: t.settings.save }) as HTMLButtonElement;
}

afterEach(() => {
  vi.useRealTimers();
});

describe('/settings', () => {
  it('показывает сохранённые значения профиля', async () => {
    installFetchMock(authorized);
    await openSettings();

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

    const timezone = await openSettings();
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

    const timezone = await openSettings();
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

    const timezone = await openSettings();
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
    expect(alert).toHaveTextContent(t.errors.network);
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

    const timezone = await openSettings();
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

    const timezone = await openSettings();
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

    await openSettings();
    await user.type(screen.getByLabelText(t.settings.timezoneSearchLabel), 'такой зоны нет');

    expect(await screen.findByText(t.settings.timezoneSearchEmpty)).toBeInTheDocument();
  });

  it('незнакомая движку зона предупреждает, но не роняет экран', async () => {
    // Наборы имён IANA у браузера и у сервера расходятся по псевдонимам. Имя взято
    // заведомо несуществующее: любое настоящее знает то один движок, то другой.
    const alien = { ...TEST_USER, timezone: 'Mars/Olympus' };
    installFetchMock({
      [SESSION]: () => jsonResponse(200, alien),
      [PROFILE]: () => jsonResponse(200, alien),
    });

    const timezone = await openSettings();

    expect(screen.getByText(t.settings.timezoneUnknown('Mars/Olympus'))).toBeInTheDocument();
    // Сохранённое значение остаётся выбранным: подменять его на похожее нельзя.
    expect(timezone).toHaveValue('Mars/Olympus');
    // Время всё равно показано — по часам компьютера.
    expect(
      screen.getByText(new RegExp(`^${t.settings.previewNow('')}\\d{2}\\.\\d{2}\\.\\d{4}`)),
    ).toBeInTheDocument();
    expect(saveButton()).toBeDisabled();
  });
});
