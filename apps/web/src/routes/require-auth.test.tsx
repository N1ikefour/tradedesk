import { screen } from '@testing-library/react';
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

  it('вошедший пользователь видит защищённый маршрут', async () => {
    installFetchMock({ [ME]: () => jsonResponse(200, TEST_USER) });
    renderApp(['/journal']);

    expect(await screen.findByRole('heading', { name: t.pages.journal })).toBeInTheDocument();
  });
});
