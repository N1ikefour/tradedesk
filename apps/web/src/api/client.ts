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
/**
 * Предел ожидания ответа на чтение (X-13: общего таймаута у клиента не было нигде).
 * Соединение, которое приняли и не ответили — `api` поднялся, но ещё не отвечает,
 * прокси в середине, уснувший туннель VPN, — не падает вовсе, и экран остаётся в
 * «Загрузка…» насовсем. Тридцать секунд здесь значат не «медленно», а «уже не ответит»:
 * API живёт на этой же машине, и самый тяжёлый его ответ — страница журнала.
 */
const READ_TIMEOUT_MS = 30_000;

/**
 * Предел ставится **только на чтение**. Оборванная мутация неотличима от применённой:
 * сервер мог её выполнить, а клиент об этом уже не узнает, — поэтому вслепую обрывать
 * запись дороже, чем ждать. Там, где предел записи нужен, его ставит вызывающий со своим
 * смыслом и своим текстом (`journal/api.ts`, автосохранение карточки).
 *
 * Сигнал вызывающего не теряется: оба объединяются, и побеждает сработавший первым.
 */
function withReadTimeout(request: Request): Request {
  if (request.method !== 'GET') {
    return request;
  }
  if (typeof AbortSignal.timeout !== 'function' || typeof AbortSignal.any !== 'function') {
    return request;
  }
  return new Request(request, {
    signal: AbortSignal.any([request.signal, AbortSignal.timeout(READ_TIMEOUT_MS)]),
  });
}

export const api = createClient<paths>({
  baseUrl: window.location.origin,
  credentials: 'same-origin',
  // openapi-fetch запоминает `globalThis.fetch` в момент создания клиента. Клиент —
  // модульный синглтон, то есть создаётся раньше любого теста, и подменённый в тесте
  // fetch до него уже не доходил бы: тесты молча ходили бы в настоящую сеть.
  fetch: (request) => globalThis.fetch(withReadTimeout(request)),
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
