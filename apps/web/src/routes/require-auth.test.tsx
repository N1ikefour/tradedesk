import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { t } from '@/i18n';
import { errorResponse, installFetchMock, jsonResponse } from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';

const ME = 'GET /api/v1/auth/me';

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

    // Соединение восстановилось, и следующий шаг это доказал: «проверьте соединение»
    // не должно висеть поверх экрана, который только что сходил на сервер.
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
