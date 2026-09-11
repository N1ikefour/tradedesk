/**
 * Ошибки API — SPEC.md 5.1, формат `{"error": {code, message, details}}`.
 *
 * Типы берутся из сгенерированной схемы (`make types`), рукописных копий контракта здесь
 * нет: словарь кодов ниже объявлен через `satisfies`, поэтому переименование кода на
 * бэкенде роняет `npm run typecheck`, а не проявляется на экране пользователя.
 */
import type { components } from '@/api/schema';

export type ErrorCode = components['schemas']['ErrorCode'];
export type ApiErrorBody = components['schemas']['ApiError'];

/** Коды, которые фронт различает по смыслу. Проверяются схемой на этапе сборки. */
export const ERROR_CODE = {
  validation: 'validation_error',
  unauthorized: 'unauthorized',
  forbiddenOrigin: 'forbidden_origin',
  notFound: 'not_found',
  positionNotFound: 'position_not_found',
  invalidCode: 'invalid_code',
  tooManyAttempts: 'too_many_attempts',
  rateLimited: 'rate_limited',
  accountNotFound: 'account_not_found',
  accountAlreadyExists: 'account_already_exists',
  accountArchived: 'account_archived',
  accountPaused: 'account_paused',
  notMt5Account: 'not_mt5_account',
} as const satisfies Record<string, ErrorCode>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Ответ с кодом ошибки. `code` может быть неизвестным: схема шире, чем набор выше. */
export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly details: Readonly<Record<string, unknown>>;

  constructor(
    status: number,
    code: string | null,
    message: string,
    details: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /**
   * `details.fields` из ответа 400 `validation_error` — SPEC.md 5.1. Ключи приходят с
   * приставкой места в запросе (`body.email`), поэтому искать поле надо по `fieldError`.
   */
  get fields(): Readonly<Record<string, string>> {
    const raw = this.details['fields'];
    if (!isRecord(raw)) {
      return {};
    }
    const result: Record<string, string> = {};
    for (const [key, value] of Object.entries(raw)) {
      if (typeof value === 'string') {
        result[key] = value;
      }
    }
    return result;
  }

  /** Сообщение по имени поля: совпадение целиком или последним сегментом (`body.email`). */
  fieldError(name: string): string | null {
    const suffix = `.${name}`;
    for (const [key, value] of Object.entries(this.fields)) {
      if (key === name || key.endsWith(suffix)) {
        return value;
      }
    }
    return null;
  }

  /** `details.retry_after` из ответа 429 — секунды до следующей попытки. */
  get retryAfter(): number | null {
    const value = this.details['retry_after'];
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      return null;
    }
    return Math.max(0, Math.ceil(value));
  }
}

/** Запрос не доехал: сеть, отменённое соединение, недоступный сервер. */
export class NetworkError extends Error {
  constructor(cause: unknown) {
    super('network request failed', { cause });
    this.name = 'NetworkError';
  }

  /**
   * Запрос оборвали мы сами — по своему пределу ожидания, а не сетью. Нужен он ради
   * записи: оборванную мутацию сервер мог уже применить, и «проверьте соединение»
   * отправляло бы чинить то, что не сломано.
   *
   * ⚠️ Читателя два, и они расходятся намеренно. `isServerUnreachable` этот признак
   * игнорирует: у чтения нет побочных эффектов, и для гейта сессии молчавшее полминуты
   * соединение неотличимо от мёртвого. А `messageForError` проверяет его первым, то есть
   * на экранах со списками оборванное чтение объясняется как «не ответил вовремя», а не
   * как «TradeDesk не отвечает». Так было и до `X-42`; менять это — решение принципала,
   * а не правка, потому что оно меняет то, что человек читает на рабочем экране.
   */
  get timedOut(): boolean {
    const reason = this.cause;
    if (!(reason instanceof DOMException)) {
      return false;
    }
    return reason.name === 'TimeoutError' || reason.name === 'AbortError';
  }
}

const SERVER_ERROR_STATUS = 500;

/**
 * Отвечало не наше API, а значит приложение не поднято. Два признака, и оба однозначные:
 * ответа не пришло вовсе, либо на 5xx не пришло тело SPEC.md 5.1 — так отвечает прокси
 * перед `api`, пока контейнер `api` стартует (в профиле `local` это dev-сервер vite, в
 * `prod` — Caddy), а не само API.
 *
 * «Ответа не пришло вовсе» включает и чтение, оборванное нашим же пределом ожидания:
 * предел стоит только на GET (`api/client.ts`), у чтения нет побочных эффектов, и
 * молчавшее тридцать секунд соединение от мёртвого человеку ничем не отличается. Пока
 * `timedOut` исключался отсюда, молчащая проверка сессии уводила на /login со словами
 * «сервер ответил ошибкой» — в тот самый тупик, ради которого X-42 и заводилась.
 * Оборванной **записи** это не касается: `messageForError` проверяет `timedOut` раньше,
 * и текст «запрос мог и дойти» остаётся за ней.
 *
 * Настоящий отказ API отличим по коду: `internal_error` с телом значит, что сервер жив и
 * сломался внутри, и звать человека проверять Docker Desktop там было бы неправдой.
 */
export function isServerUnreachable(error: unknown): boolean {
  if (error instanceof NetworkError) {
    return true;
  }
  return (
    error instanceof ApiRequestError && error.status >= SERVER_ERROR_STATUS && error.code === null
  );
}

/**
 * Тело ответа с ошибкой → `ApiRequestError`. Тело приходит как `unknown`: обещание схемы
 * проверяется здесь один раз, чтобы дальше по коду ошибка была одной формы.
 */
export function toApiRequestError(status: number, payload: unknown): ApiRequestError {
  if (isRecord(payload) && isRecord(payload['error'])) {
    const error = payload['error'];
    const code = typeof error['code'] === 'string' ? error['code'] : null;
    const message = typeof error['message'] === 'string' ? error['message'] : '';
    const details = isRecord(error['details']) ? error['details'] : {};
    return new ApiRequestError(status, code, message, details);
  }
  return new ApiRequestError(status, null, '', {});
}
