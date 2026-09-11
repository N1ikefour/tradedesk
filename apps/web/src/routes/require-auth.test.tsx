import { onlineManager } from '@tanstack/react-query';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';

import { t } from '@/i18n';
import { errorResponse, installFetchMock, jsonResponse } from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';
import { setTabHidden } from '@/test/tab-visibility';

const ME = 'GET /api/v1/auth/me';
const ACCOUNTS = 'GET /api/v1/accounts';

/** Повтор запроса сессии откладывается на секунду — ожидание должно её пережить. */
const AFTER_RETRY_MS = 5000;

/** Страница ошибки прокси: `502` без тела SPEC.md 5.1 — так отвечает Caddy, пока api не встал. */
function gatewayError(): Response {
  return new Response('<html>502 Bad Gateway</html>', {
    status: 502,
    headers: { 'content-type': 'text/html' },
  });
}

afterEach(() => {
  // Оба состояния глобальные: оставленные, они подвесили бы соседние тесты.
  onlineManager.setOnline(true);
  setTabHidden(false);
});

describe('RequireAuth', () => {
  it('401 при загрузке защищённой страницы уводит на /login', async () => {
    installFetchMock({ [ME]: () => errorResponse(401, 'unauthorized', 'Требуется вход') });
    renderApp(['/journal']);

    expect(await screen.findByRole('heading', { name: t.login.title })).toBeInTheDocument();
    // Защищённый экран не должен успеть показаться ни на кадр.
    expect(screen.queryByRole('heading', { name: t.pages.journal })).not.toBeInTheDocument();
  });

  it('пока сессия неизвестна, защищённый экран не рисуется', () => {
    installFetchMock({ [ME]: () => new Promise<Response>(() => {}) });
    renderApp(['/journal']);

    expect(screen.getByRole('status')).toHaveTextContent(t.common.loading);
    expect(screen.queryByRole('heading', { name: t.pages.journal })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: t.login.title })).not.toBeInTheDocument();
  });

  it('неудачный запрос сессии — это не «не вошёл»: причина объясняется', async () => {
    // Один повтор настроен на самом запросе сессии, поэтому 500 приходит дважды.
    installFetchMock({ [ME]: () => errorResponse(500, 'internal_error', 'Внутренняя ошибка') });
    renderApp(['/journal']);

    // Повтор откладывается на секунду, поэтому ожидание длиннее умолчания.
    const title = await screen.findByRole('heading', { name: t.login.title }, { timeout: 5000 });
    expect(title).toBeInTheDocument();
    expect(await screen.findByRole('alert')).toHaveTextContent(t.login.sessionCheckFailed);
    expect(screen.queryByRole('heading', { name: t.pages.journal })).not.toBeInTheDocument();
  });

  it('объяснение сбоя не переживает свою причину', async () => {
    let sessionFails = true;
    installFetchMock({
      [ME]: () =>
        sessionFails
          ? errorResponse(502, 'internal_error', 'Bad gateway')
          : errorResponse(401, 'unauthorized', 'Требуется вход'),
      'POST /api/v1/auth/request-code': () => jsonResponse(202, { status: 'accepted' }),
    });
    const user = userEvent.setup();
    renderApp(['/journal']);

    const alert = await screen.findByRole('alert', {}, { timeout: 5000 });
    expect(alert).toHaveTextContent(t.login.sessionCheckFailed);

    // Сервер снова отвечает, и следующий шаг это доказал: объяснение сбоя не должно
    // висеть поверх экрана, который только что сходил на сервер.
    sessionFails = false;
    await user.type(screen.getByLabelText(t.login.emailLabel), TEST_USER.email);
    await user.click(screen.getByRole('button', { name: t.login.requestCode }));
    await screen.findByLabelText(t.login.codeLabel);

    expect(screen.queryByText(t.login.sessionCheckFailed)).not.toBeInTheDocument();
  });

  it('вошедший пользователь видит защищённый маршрут', async () => {
    installFetchMock({ [ME]: () => jsonResponse(200, TEST_USER) });
    renderApp(['/journal']);

    expect(await screen.findByRole('heading', { name: t.pages.journal })).toBeInTheDocument();
  });
});

describe('три состояния связи вместо одной «Загрузки…» (X-13, X-42)', () => {
  it('браузер офлайн не мешает войти: API живёт на этой же машине', async () => {
    // X-42. По умолчанию библиотека **не отправляет** запрос, пока браузер считает себя
    // офлайн, и экран остаётся в «Загрузка…» навсегда. Здесь это было бы прямым враньём:
    // Wi-Fi выключен, а `localhost` жив и отвечает. В jsdom `navigator.onLine` всегда
    // `true`, поэтому положение дел задаёт `onlineManager` — не падающий `fetch`: это
    // разные вещи, и мокнутый отказ паузы не воспроизводит вовсе.
    installFetchMock({
      [ME]: () => jsonResponse(200, TEST_USER),
      [ACCOUNTS]: () => jsonResponse(200, { items: [] }),
    });
    onlineManager.setOnline(false);
    renderApp(['/journal']);

    expect(await screen.findByRole('heading', { name: t.pages.journal })).toBeInTheDocument();
  });

  it('офлайн и мёртвый API — это отказ с объяснением, а не вечная загрузка', async () => {
    installFetchMock({
      [ME]: () => {
        throw new TypeError('Failed to fetch');
      },
    });
    onlineManager.setOnline(false);
    renderApp(['/journal']);

    expect(
      await screen.findByText(t.connection.serverDownTitle, {}, { timeout: AFTER_RETRY_MS }),
    ).toBeInTheDocument();
    expect(screen.queryByText(t.common.loading)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: t.common.retry })).toBeEnabled();
  });

  it('приложение не поднято: экран остаётся на месте и зовёт запустить Docker Desktop', async () => {
    // Самый частый утренний отказ этой установки (SETUP.md 8): страницу открыли раньше,
    // чем Docker Desktop поднял контейнеры. Прокси отвечает `502` без тела SPEC.md 5.1 —
    // раньше это попадало в общее «что-то пошло не так» и уводило на /login, где форма
    // входа ходит на тот же недоступный API.
    let apiUp = false;
    installFetchMock({
      [ME]: () => (apiUp ? jsonResponse(200, TEST_USER) : gatewayError()),
      [ACCOUNTS]: () => jsonResponse(200, { items: [] }),
    });
    const user = userEvent.setup();
    const { router } = renderApp(['/journal']);

    expect(
      await screen.findByText(t.connection.serverDownTitle, {}, { timeout: AFTER_RETRY_MS }),
    ).toBeInTheDocument();
    expect(screen.getByText(t.connection.serverDownHint)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: t.login.title })).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/journal');

    // Докер доехал — «Повторить» возвращает человека туда, куда он шёл, без F5.
    apiUp = true;
    await user.click(screen.getByRole('button', { name: t.common.retry }));

    expect(await screen.findByRole('heading', { name: t.pages.journal })).toBeInTheDocument();
  });

  it('приостановленный запрос сессии называет себя паузой, а не загрузкой', async () => {
    // X-13. Повтор ждёт `focusManager.isFocused()`, то есть стоит, пока вкладка в фоне, и
    // сам не сдвинется. Под «Загрузка…» это выглядело зависшим приложением: наблюдалось
    // 117 секунд при одном завершённом запросе.
    installFetchMock({ [ME]: () => errorResponse(500, 'internal_error', 'Внутренняя ошибка') });
    setTabHidden(true);
    renderApp(['/journal']);

    expect(
      await screen.findByText(t.connection.pausedHint, {}, { timeout: AFTER_RETRY_MS }),
    ).toBeInTheDocument();
    expect(screen.getByText(t.connection.pausedTitle)).toBeInTheDocument();
    expect(screen.queryByText(t.common.loading)).not.toBeInTheDocument();
  });
});
