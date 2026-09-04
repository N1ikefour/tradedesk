import { focusManager, QueryClient } from '@tanstack/react-query';
import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { api, unwrap } from '@/api/client';
import { ApiRequestError } from '@/api/errors';
import {
  installUnauthorizedBridge,
  SESSION_EXPIRED_QUERY_KEY,
  SESSION_QUERY_KEY,
} from '@/auth/session';
import { t } from '@/i18n';
import { errorResponse, installFetchMock, jsonResponse } from '@/test/fetch-mock';
import { renderApp, TEST_USER } from '@/test/render';

const ME = 'GET /api/v1/auth/me';
const OUTBOX = 'GET /api/v1/dev/outbox';

function outboxRequest() {
  return unwrap(api.GET('/api/v1/dev/outbox', { params: { query: { limit: 1 } } }));
}

describe('обработка 401', () => {
  it('401 на любом запросе обнуляет сессию — не только на /auth/me', async () => {
    installFetchMock({ [OUTBOX]: () => errorResponse(401, 'unauthorized', 'Требуется вход') });
    const client = new QueryClient();
    client.setQueryData(SESSION_QUERY_KEY, TEST_USER);
    const dispose = installUnauthorizedBridge(client);

    await expect(outboxRequest()).rejects.toBeInstanceOf(ApiRequestError);

    expect(client.getQueryData(SESSION_QUERY_KEY)).toBeNull();
    expect(client.getQueryData(SESSION_EXPIRED_QUERY_KEY)).toBe(true);
    dispose();
  });

  it('без прежней сессии отметка «сессия оборвалась» не ставится', async () => {
    installFetchMock({ [OUTBOX]: () => errorResponse(401, 'unauthorized', 'Требуется вход') });
    const client = new QueryClient();
    const dispose = installUnauthorizedBridge(client);

    await expect(outboxRequest()).rejects.toBeInstanceOf(ApiRequestError);

    expect(client.getQueryData(SESSION_EXPIRED_QUERY_KEY)).toBeUndefined();
    dispose();
  });

  it('оборвавшаяся сессия уводит с защищённого экрана на /login с объяснением', async () => {
    installFetchMock({
      [ME]: () => jsonResponse(200, TEST_USER),
      [OUTBOX]: () => errorResponse(401, 'unauthorized', 'Требуется вход'),
      'POST /api/v1/auth/request-code': () => jsonResponse(202, { status: 'accepted' }),
    });
    renderApp(['/journal']);
    await screen.findByRole('heading', { name: t.pages.journal });

    await act(async () => {
      await outboxRequest().catch(() => undefined);
    });

    expect(await screen.findByRole('heading', { name: t.login.title })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(t.login.sessionExpired);

    // Тот же класс, что и у сбоя проверки: объяснение перехода не должно пережить
    // следующий успешный шаг.
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(t.login.emailLabel), TEST_USER.email);
    await user.click(screen.getByRole('button', { name: t.login.requestCode }));
    await screen.findByLabelText(t.login.codeLabel);

    expect(screen.queryByText(t.login.sessionExpired)).not.toBeInTheDocument();
  });

  it('возврат во вкладку перепроверяет сессию и замечает, что её погасили', async () => {
    let authorized = true;
    installFetchMock({
      [ME]: () =>
        authorized
          ? jsonResponse(200, TEST_USER)
          : errorResponse(401, 'unauthorized', 'Требуется вход'),
    });
    renderApp(['/journal']);
    await screen.findByRole('heading', { name: t.pages.journal });

    // Сессию гасят на сервере, пока вкладка лежит в фоне.
    authorized = false;

    // Запрос сессии свежий 30 секунд, иначе возврат фокуса ничего не перечитывает.
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(Date.now() + 60_000);
    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });

    expect(await screen.findByRole('heading', { name: t.login.title })).toBeInTheDocument();
  });
});

afterEach(() => {
  vi.useRealTimers();
  // Менеджер фокуса — глобальный синглтон react-query: оставленное значение
  // просочилось бы в следующий тест.
  focusManager.setFocused(undefined);
});
