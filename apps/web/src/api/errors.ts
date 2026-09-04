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
  invalidCode: 'invalid_code',
  tooManyAttempts: 'too_many_attempts',
  rateLimited: 'rate_limited',
} as const satisfies Record<string, ErrorCode>;

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
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
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
