import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

import { CODE_TTL_MS, rememberCodeRequest } from '@/auth/code-request';
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
const OUTBOX = 'GET /api/v1/dev/outbox';
const LOGOUT = 'POST /api/v1/auth/logout';

const anonymous: RouteTable = {
  [ME]: () => errorResponse(401, 'unauthorized', 'Требуется вход'),
  [REQUEST_CODE]: () => jsonResponse(202, { status: 'accepted' }),
};

async function fillEmailAndAdvance(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(t.login.emailLabel), TEST_USER.email);
  await user.click(screen.getByRole('button', { name: t.login.requestCode }));
  await screen.findByLabelText(t.login.codeLabel);
}

// Хранилище окна общее на весь файл — так же, как `localStorage` у соседей
// (`selection.test.ts`, `theme.test.ts`): незаконченная попытка входа из предыдущего
// теста иначе поднимала бы следующий сразу на шаге ввода кода.
beforeEach(() => {
  window.sessionStorage.clear();
});

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

  it('успешный запрос кода снимает алерт лимита', async () => {
    let limited = true;
    installFetchMock({
      [ME]: () => errorResponse(401, 'unauthorized', 'Требуется вход'),
      // 429 без retry_after: счётчика нет, кнопка не заблокирована — повтор возможен
      // сразу, и старый алерт не должен пережить удавшийся запрос.
      [REQUEST_CODE]: () => {
        if (limited) {
          limited = false;
          return errorResponse(429, 'rate_limited', 'Слишком часто');
        }
        return jsonResponse(202, { status: 'accepted' });
      },
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    await user.type(screen.getByLabelText(t.login.emailLabel), TEST_USER.email);
    await user.click(screen.getByRole('button', { name: t.login.requestCode }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      t.errors.rateLimitedUnknownDelayFor(TEST_USER.email),
    );

    await user.click(screen.getByRole('button', { name: t.login.requestCode }));
    await screen.findByLabelText(t.login.codeLabel);

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('уход на письма и возврат сохраняют шаг ввода кода', async () => {
    const { calls } = installFetchMock({
      ...anonymous,
      [OUTBOX]: () => jsonResponse(200, { items: [] }),
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    await fillEmailAndAdvance(user);

    // Ровно тот путь, которым сейчас и добывают код: страница писем — соседний
    // маршрут, и форма входа на нём размонтируется (X-16).
    await user.click(screen.getByRole('link', { name: t.login.devOutboxLink }));
    await screen.findByRole('heading', { name: t.outbox.title });
    await user.click(screen.getByRole('link', { name: t.outbox.backToLogin }));

    expect(await screen.findByLabelText(t.login.codeLabel)).toBeInTheDocument();
    expect(screen.getByText(t.login.codeStepHint(TEST_USER.email))).toBeInTheDocument();
    // Код за поход на письма второй раз не запрашивается.
    expect(calls.filter((call) => call.path === '/api/v1/auth/request-code')).toHaveLength(1);
  });

  it('истёкший код не восстанавливается: первый шаг и объяснение, адрес сохранён', async () => {
    installFetchMock(anonymous);
    // Отметка старше срока жизни кода (SPEC.md §4 — 10 минут).
    rememberCodeRequest(TEST_USER.email, Date.now() - CODE_TTL_MS - 1);
    renderApp(['/login']);

    expect(await screen.findByRole('alert')).toHaveTextContent(t.login.codeExpired);
    expect(screen.getByLabelText(t.login.emailLabel)).toHaveValue(TEST_USER.email);
    expect(screen.queryByLabelText(t.login.codeLabel)).not.toBeInTheDocument();
  });

  it('отметка из будущего не восстанавливает шаг: разность отрицательна, но код мёртв', async () => {
    installFetchMock(anonymous);
    // Часы ушли вперёд, код запрошен, часы поправили. Простая проверка «прошло ли TTL»
    // на такой отметке ложна всегда и держала бы шаг кода до закрытия вкладки.
    rememberCodeRequest(TEST_USER.email, Date.now() + 60 * 60 * 1000);
    renderApp(['/login']);

    expect(await screen.findByRole('alert')).toHaveTextContent(t.login.codeExpired);
    expect(screen.getByLabelText(t.login.emailLabel)).toHaveValue(TEST_USER.email);
    expect(screen.queryByLabelText(t.login.codeLabel)).not.toBeInTheDocument();
  });

  it('too_many_attempts отменяет попытку — возврат с писем не выдаёт код за годный', async () => {
    installFetchMock({
      ...anonymous,
      [VERIFY]: () => errorResponse(422, 'too_many_attempts', 'Попытки исчерпаны'),
      [OUTBOX]: () => jsonResponse(200, { items: [] }),
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    await fillEmailAndAdvance(user);
    await user.type(screen.getByLabelText(t.login.codeLabel), '222222');
    expect(await screen.findByRole('alert')).toHaveTextContent(t.errors.tooManyAttempts);

    await user.click(screen.getByRole('link', { name: t.login.devOutboxLink }));
    await screen.findByRole('heading', { name: t.outbox.title });
    await user.click(screen.getByRole('link', { name: t.outbox.backToLogin }));

    // Код погашен сервером: шаг ввода с пустым полем изображал бы работающую попытку.
    expect(await screen.findByLabelText(t.login.emailLabel)).toBeInTheDocument();
    expect(screen.queryByLabelText(t.login.codeLabel)).not.toBeInTheDocument();
  });

  it('«изменить адрес» отменяет попытку — возврат с писем не тащит её обратно', async () => {
    installFetchMock({
      ...anonymous,
      [OUTBOX]: () => jsonResponse(200, { items: [] }),
    });
    const user = userEvent.setup();
    renderApp(['/login']);

    await fillEmailAndAdvance(user);
    await user.click(screen.getByRole('button', { name: t.login.changeEmail }));

    await user.click(screen.getByRole('link', { name: t.login.devOutboxLink }));
    await screen.findByRole('heading', { name: t.outbox.title });
    await user.click(screen.getByRole('link', { name: t.outbox.backToLogin }));

    expect(await screen.findByLabelText(t.login.emailLabel)).toBeInTheDocument();
    expect(screen.queryByLabelText(t.login.codeLabel)).not.toBeInTheDocument();
  });

  it('выход не оставляет незаконченную попытку входа', async () => {
    installFetchMock({
      [ME]: () => jsonResponse(200, TEST_USER),
      [LOGOUT]: () => emptyResponse(204),
    });
    // Попытка, до которой руки не дошли: её код давно погашен входом.
    rememberCodeRequest(TEST_USER.email, Date.now());
    const user = userEvent.setup();
    renderApp(['/']);

    await screen.findByRole('heading', { name: t.pages.dashboard });
    await user.click(screen.getByRole('button', { name: t.header.logout }));

    expect(await screen.findByLabelText(t.login.emailLabel)).toBeInTheDocument();
    expect(screen.queryByLabelText(t.login.codeLabel)).not.toBeInTheDocument();
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
