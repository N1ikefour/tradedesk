import { describe, expect, it, vi } from 'vitest';

import { api, unwrap, unwrapEmpty } from '@/api/client';
import { messageForError } from '@/api/error-message';
import { NetworkError } from '@/api/errors';
import { t } from '@/i18n';
import { stubAbortTimeout, timeoutReason } from '@/test/abort-timeout';
import { emptyResponse, installFetchMock, type MockedCall } from '@/test/fetch-mock';

/**
 * Соединение, которое приняли и не ответили: ни данных, ни ошибки. Закончиться оно может
 * только обрывом, поэтому обрыв здесь единственный выход из промиса.
 */
function silent({ signal }: { signal: AbortSignal | null }): Promise<Response> {
  return new Promise<Response>((_, reject) => {
    if (signal?.aborted === true) {
      reject(timeoutReason());
      return;
    }
    signal?.addEventListener('abort', () => reject(timeoutReason()));
  });
}

/** Обрывать раньше, чем запрос ушёл, бессмысленно: обрывать было бы нечего. */
async function requestSent(calls: MockedCall[]): Promise<void> {
  await vi.waitFor(() => expect(calls).not.toHaveLength(0));
}

describe('предел ожидания чтения', () => {
  it('молчащее чтение обрывается своим пределом, а не висит в «Загрузка…»', async () => {
    // X-13: таймаута у клиента не было нигде, и запрос, оставшийся без ответа, держал
    // `isPending` столько же, сколько висел сам. Ни один экран из такого не выходит.
    const timeout = new AbortController();
    const restore = stubAbortTimeout(timeout.signal);
    try {
      const { calls } = installFetchMock({ 'GET /api/v1/auth/me': silent });
      const call = unwrap(api.GET('/api/v1/auth/me')).catch((error: unknown) => error);
      await requestSent(calls);

      timeout.abort(timeoutReason());
      const error = await call;

      expect(error).toBeInstanceOf(NetworkError);
      expect((error as NetworkError).timedOut).toBe(true);
      // Текст отличается от «приложение не поднято»: соединение могло быть цело.
      expect(messageForError(error)).toBe(t.errors.timeout);
    } finally {
      restore();
    }
  });

  it('запись тем же пределом не обрывается', async () => {
    // Оборванная мутация неотличима от применённой: сервер мог её выполнить, а клиент об
    // этом уже не узнает. Предел записи ставит вызывающий со своим смыслом и своим текстом
    // (`journal/api.ts`), а общий предел чтения до записи не достаёт.
    const timeout = new AbortController();
    const restore = stubAbortTimeout(timeout.signal);
    try {
      let answer: (response: Response) => void = () => {};
      const { calls } = installFetchMock({
        'POST /api/v1/auth/logout': ({ signal }) =>
          new Promise<Response>((resolve, reject) => {
            answer = resolve;
            signal?.addEventListener('abort', () => reject(timeoutReason()));
          }),
      });
      const call = unwrapEmpty(api.POST('/api/v1/auth/logout'));
      await requestSent(calls);

      timeout.abort(timeoutReason());
      answer(emptyResponse(204));

      await expect(call).resolves.toBeUndefined();
    } finally {
      restore();
    }
  });
});
