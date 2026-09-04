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

    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errors.rateLimitedFor(TEST_USER.email, 42),
    );
    expect(screen.getByRole('button', { name: t.login.requestCode })).toBeDisabled();
  });

  it('лимит держит только тот адрес, который в него упёрся', async () => {
    installFetchMock({
      [ME]: () => errorResponse(401, 'unauthorized', 'Требуется вход'),
      [REQUEST_CODE]: ({ body }) =>
        (body as { email: string }).email === TEST_USER.email
          ? errorResponse(429, 'rate_limited', 'Слишком часто', { retry_after: 600 })
          : jsonResponse(202, { status: 'accepted' }),
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    const emailField = screen.getByLabelText(t.login.emailLabel);
    await user.type(emailField, TEST_USER.email);
    await user.click(screen.getByRole('button', { name: t.login.requestCode }));
    await screen.findByRole('alert');
    expect(screen.getByRole('button', { name: t.login.requestCode })).toBeDisabled();

    // Самый вероятный путь к лимиту — опечатка в адресе; исправление должно помогать
    // сразу, а не через десять минут ожидания.
    await user.clear(emailField);
    await user.type(emailField, 'other@example.com');

    expect(screen.getByRole('button', { name: t.login.requestCode })).toBeEnabled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: t.login.requestCode }));
    expect(await screen.findByLabelText(t.login.codeLabel)).toBeInTheDocument();
  });

  it('«Изменить адрес» после лимита не оставляет форму заблокированной', async () => {
    installFetchMock({
      [ME]: () => errorResponse(401, 'unauthorized', 'Требуется вход'),
      [REQUEST_CODE]: ({ body }) =>
        (body as { email: string }).email === TEST_USER.email
          ? jsonResponse(202, { status: 'accepted' })
          : jsonResponse(202, { status: 'accepted' }),
      'POST /api/v1/auth/verify': () => errorResponse(422, 'invalid_code', 'Неверный код'),
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    await fillEmailAndAdvance(user);
    await user.click(screen.getByRole('button', { name: t.login.changeEmail }));

    const emailField = await screen.findByLabelText(t.login.emailLabel);
    expect(emailField).toHaveValue(TEST_USER.email);
    expect(screen.getByRole('button', { name: t.login.requestCode })).toBeEnabled();
  });

  it('таймер выше полутора минут показывается минутами, а не сырыми секундами', async () => {
    installFetchMock({
      [ME]: () => errorResponse(401, 'unauthorized', 'Требуется вход'),
      [REQUEST_CODE]: () =>
        errorResponse(429, 'rate_limited', 'Слишком часто', { retry_after: 522 }),
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    await user.type(screen.getByLabelText(t.login.emailLabel), TEST_USER.email);
    await user.click(screen.getByRole('button', { name: t.login.requestCode }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('8 минут 42 секунды');
    expect(alert).not.toHaveTextContent('522');
  });

  it('повторная отправка кода подтверждается сообщением', async () => {
    installFetchMock({
      ...anonymous,
      [VERIFY]: () => errorResponse(422, 'too_many_attempts', 'Попытки исчерпаны'),
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    await fillEmailAndAdvance(user);
    await user.type(screen.getByLabelText(t.login.codeLabel), '222222');
    await screen.findByRole('alert');

    await user.click(screen.getByRole('button', { name: t.login.resend }));

    expect(await screen.findByRole('alert')).toHaveTextContent(t.login.codeResent(TEST_USER.email));
  });

  it('validation_error показывает сообщение у поля, а не общий текст', async () => {
    installFetchMock({
      [ME]: () => errorResponse(401, 'unauthorized', 'Требуется вход'),
      [REQUEST_CODE]: () =>
        errorResponse(400, 'validation_error', 'Ошибка валидации', {
          fields: { 'body.email': 'Некорректный адрес электронной почты' },
        }),
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    const emailField = screen.getByLabelText(t.login.emailLabel);
    await user.type(emailField, 'не-адрес');
    await user.click(screen.getByRole('button', { name: t.login.requestCode }));

    expect(await screen.findByText('Некорректный адрес электронной почты')).toBeInTheDocument();
    expect(emailField).toHaveAttribute('aria-invalid', 'true');
    expect(screen.queryByText(t.errors.validation)).not.toBeInTheDocument();
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

    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errors.rateLimitedUnknownDelayFor(TEST_USER.email),
    );
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
