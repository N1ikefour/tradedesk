import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { SESSION_QUERY_KEY } from '@/auth/session';
import { t } from '@/i18n';
import { errorResponse, installFetchMock, jsonResponse } from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';

const OUTBOX = 'GET /api/v1/dev/outbox';

const letter = {
  id: '0199a2b0-0000-7000-8000-0000000000aa',
  to_email: 'trader@example.com',
  subject: 'Код для входа в TradeDesk',
  body_text: 'Ваш код: 314159. Он действует 10 минут.',
  body_html: null,
  created_at: '2026-09-02T12:03:00Z',
};

describe('/dev/outbox', () => {
  it('показывает письмо с кодом целиком', async () => {
    installFetchMock({ [OUTBOX]: () => jsonResponse(200, { items: [letter] }) });
    renderApp(['/dev/outbox']);

    expect(await screen.findByText(letter.subject)).toBeInTheDocument();
    // Код должен быть виден глазами: за ним человек сюда и приходит.
    expect(screen.getByText(letter.body_text)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(letter.to_email))).toBeInTheDocument();
  });

  it('пустой ящик объясняет, что делать', async () => {
    installFetchMock({ [OUTBOX]: () => jsonResponse(200, { items: [] }) });
    renderApp(['/dev/outbox']);

    expect(await screen.findByText(t.outbox.empty)).toBeInTheDocument();
  });

  it('ошибка загрузки показывается, а не проглатывается', async () => {
    installFetchMock({ [OUTBOX]: () => errorResponse(500, 'internal_error', 'Внутренняя ошибка') });
    renderApp(['/dev/outbox']);

    expect(await screen.findByRole('alert')).toHaveTextContent(t.outbox.loadFailed);
  });

  it('страница открыта без входа: /auth/me не запрашивается', async () => {
    const { calls } = installFetchMock({ [OUTBOX]: () => jsonResponse(200, { items: [] }) });
    renderApp(['/dev/outbox']);

    await screen.findByText(t.outbox.empty);
    expect(calls.some((call) => call.path === '/api/v1/auth/me')).toBe(false);
  });

  it('дата письма идёт в таймзоне пользователя, когда сессия уже в кэше', async () => {
    const { calls } = installFetchMock({ [OUTBOX]: () => jsonResponse(200, { items: [letter] }) });
    const { client } = renderApp(['/dev/outbox']);
    await screen.findByText(letter.subject);

    // Профиль страница не запрашивает — берёт из кэша, если он уже наполнен входом.
    // 12:03 UTC — это 21:03 в Токио.
    act(() => {
      client.setQueryData(SESSION_QUERY_KEY, { ...TEST_USER, timezone: 'Asia/Tokyo' });
    });

    expect(await screen.findByText(/02\.09\.2026 21:03/)).toBeInTheDocument();
    expect(calls.some((call) => call.path === '/api/v1/auth/me')).toBe(false);
  });

  it('кнопка «Обновить» перечитывает ящик', async () => {
    const { calls } = installFetchMock({ [OUTBOX]: () => jsonResponse(200, { items: [] }) });
    const user = userEvent.setup();
    renderApp(['/dev/outbox']);

    await screen.findByText(t.outbox.empty);
    const before = calls.filter((call) => call.path === '/api/v1/dev/outbox').length;
    await user.click(screen.getByRole('button', { name: t.outbox.refresh }));

    expect(calls.filter((call) => call.path === '/api/v1/dev/outbox').length).toBeGreaterThan(
      before,
    );
  });
});
