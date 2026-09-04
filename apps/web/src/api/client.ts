/**
 * Единственный клиент API. Пути и тела типизированы сгенерированной схемой
 * (`src/api/schema.d.ts`, цель `make types`) — рукописных описаний эндпоинтов нет.
 */
import createClient, { type Middleware } from 'openapi-fetch';

import { NetworkError, toApiRequestError } from '@/api/errors';
import type { paths } from '@/api/schema';

// Пути в схеме уже содержат префикс /api/v1, поэтому база — только origin страницы.
// Он же обязателен явно: openapi-fetch строит `new Request(url)`, а тот требует
// абсолютный адрес. Свой origin и никакой другой: cookie сессии httpOnly и ходит
// только на своё происхождение (SPEC.md 4), а /api туда доводит прокси.
export const api = createClient<paths>({
  baseUrl: window.location.origin,
  credentials: 'same-origin',
  // openapi-fetch запоминает `globalThis.fetch` в момент создания клиента. Клиент —
  // модульный синглтон, то есть создаётся раньше любого теста, и подменённый в тесте
  // fetch до него уже не доходил бы: тесты молча ходили бы в настоящую сеть.
  fetch: (request) => globalThis.fetch(request),
});

type UnauthorizedHandler = () => void;

let unauthorizedHandler: UnauthorizedHandler | null = null;

/**
 * 401 обрабатывается один раз на всё приложение: компоненты про него не знают.
 * Обработчик регистрирует корень (`AuthProvider`), он же уводит на /login.
 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

const unauthorizedMiddleware: Middleware = {
  onResponse({ response }) {
    if (response.status === 401) {
      unauthorizedHandler?.();
    }
    return undefined;
  },
};

api.use(unauthorizedMiddleware);

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

/**
 * Ответ openapi-fetch → значение или исключение. Два разных провала — ответ с ошибкой
 * и несостоявшийся запрос — приводятся к двум классам, а не к одному «что-то не так».
 */
export async function unwrap<T>(call: Promise<FetchResult<T>>): Promise<T> {
  let result: FetchResult<T>;
  try {
    result = await call;
  } catch (cause) {
    throw new NetworkError(cause);
  }
  if (result.error !== undefined) {
    throw toApiRequestError(result.response.status, result.error);
  }
  if (result.data === undefined) {
    throw toApiRequestError(result.response.status, null);
  }
  return result.data;
}

/** То же для ответов без тела (204). */
export async function unwrapEmpty(call: Promise<FetchResult<unknown>>): Promise<void> {
  let result: FetchResult<unknown>;
  try {
    result = await call;
  } catch (cause) {
    throw new NetworkError(cause);
  }
  if (result.error !== undefined) {
    throw toApiRequestError(result.response.status, result.error);
  }
}
