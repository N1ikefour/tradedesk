import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { t } from '@/i18n';
import {
  emptyResponse,
  errorResponse,
  installFetchMock,
  jsonResponse,
  type RouteTable,
} from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';

const ME = 'GET /api/v1/auth/me';
const REQUEST_CODE = 'POST /api/v1/auth/request-code';
const VERIFY = 'POST /api/v1/auth/verify';

const anonymous: RouteTable = {
  [ME]: () => errorResponse(401, 'unauthorized', 'Требуется вход'),
  [REQUEST_CODE]: () => jsonResponse(202, { status: 'accepted' }),
};

async function fillEmailAndAdvance(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(t.login.emailLabel), TEST_USER.email);
  await user.click(screen.getByRole('button', { name: t.login.requestCode }));
  await screen.findByLabelText(t.login.codeLabel);
}

describe('Login', () => {
  it('код из письма вводит пользователя и открывает дашборд', async () => {
    const { calls } = installFetchMock({
      ...anonymous,
      [VERIFY]: () => jsonResponse(200, TEST_USER),
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    await fillEmailAndAdvance(user);
    await user.type(screen.getByLabelText(t.login.codeLabel), '123456');

    // Автосабмит на шестой цифре — SPEC.md 9.3, отдельной кнопки ждать не нужно.
    expect(await screen.findByRole('heading', { name: t.pages.dashboard })).toBeInTheDocument();

    const verify = calls.find((call) => call.path === '/api/v1/auth/verify');
    expect(verify?.body).toEqual({ email: TEST_USER.email, code: '123456' });
  });

  it('invalid_code — «неверный код», поле очищается для новой попытки', async () => {
    installFetchMock({
      ...anonymous,
      [VERIFY]: () => errorResponse(422, 'invalid_code', 'Неверный код'),
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    await fillEmailAndAdvance(user);
    await user.type(screen.getByLabelText(t.login.codeLabel), '111111');

    expect(await screen.findByRole('alert')).toHaveTextContent(t.errors.invalidCode);
    expect(screen.getByLabelText(t.login.codeLabel)).toHaveValue('');
    expect(screen.queryByRole('heading', { name: t.pages.dashboard })).not.toBeInTheDocument();
  });

  it('too_many_attempts — «попытки исчерпаны», текст отличается от неверного кода', async () => {
    installFetchMock({
      ...anonymous,
      [VERIFY]: () => errorResponse(422, 'too_many_attempts', 'Попытки исчерпаны'),
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    await fillEmailAndAdvance(user);
    await user.type(screen.getByLabelText(t.login.codeLabel), '222222');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(t.errors.tooManyAttempts);
    expect(alert).not.toHaveTextContent(t.errors.invalidCode);
    // Новый код запрашивается прямо отсюда — иначе состояние тупиковое.
    expect(screen.getByRole('button', { name: t.login.resend })).toBeEnabled();
  });

  it('rate_limited — текст учитывает retry_after и запрос кода заблокирован', async () => {
    installFetchMock({
      [ME]: () => errorResponse(401, 'unauthorized', 'Требуется вход'),
      [REQUEST_CODE]: () =>
        errorResponse(429, 'rate_limited', 'Слишком часто', { retry_after: 42 }),
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    await user.type(screen.getByLabelText(t.login.emailLabel), TEST_USER.email);
    await user.click(screen.getByRole('button', { name: t.login.requestCode }));

    expect(await screen.findByRole('alert')).toHaveTextContent(t.errors.rateLimited(42));
    expect(screen.getByRole('button', { name: t.login.requestCode })).toBeDisabled();
  });

  it('rate_limited без retry_after — общий текст, а не «через null секунд»', async () => {
    installFetchMock({
      [ME]: () => errorResponse(401, 'unauthorized', 'Требуется вход'),
      [REQUEST_CODE]: () => errorResponse(429, 'rate_limited', 'Слишком часто'),
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    await user.type(screen.getByLabelText(t.login.emailLabel), TEST_USER.email);
    await user.click(screen.getByRole('button', { name: t.login.requestCode }));

    expect(await screen.findByRole('alert')).toHaveTextContent(t.errors.rateLimitedUnknownDelay);
  });

  it('выход возвращает на /login', async () => {
    installFetchMock({
      [ME]: () => jsonResponse(200, TEST_USER),
      'POST /api/v1/auth/logout': () => emptyResponse(204),
    });
    const user = userEvent.setup();
    renderApp(['/']);

    await screen.findByRole('heading', { name: t.pages.dashboard });
    await user.click(screen.getByRole('button', { name: t.header.logout }));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: t.login.title })).toBeInTheDocument();
    });
  });
});
