/**
 * Код ошибки → текст для человека. Одно место на приложение: иначе один и тот же код
 * объясняется на разных экранах по-разному.
 */
import { ApiRequestError, ERROR_CODE, NetworkError } from '@/api/errors';
import { t } from '@/i18n';

export function messageForError(error: unknown): string {
  if (error instanceof NetworkError) {
    return t.errors.network;
  }
  if (!(error instanceof ApiRequestError)) {
    return t.errors.unknown;
  }
  switch (error.code) {
    case ERROR_CODE.invalidCode:
      return t.errors.invalidCode;
    case ERROR_CODE.tooManyAttempts:
      return t.errors.tooManyAttempts;
    case ERROR_CODE.rateLimited: {
      const retryAfter = error.retryAfter;
      return retryAfter === null
        ? t.errors.rateLimitedUnknownDelay
        : t.errors.rateLimited(retryAfter);
    }
    case ERROR_CODE.validation:
      return t.errors.validation;
    case ERROR_CODE.unauthorized:
      return t.errors.unauthorized;
    case ERROR_CODE.forbiddenOrigin:
      return t.errors.forbiddenOrigin;
    case ERROR_CODE.notFound:
      return t.errors.notFound;
    default:
      return t.errors.unknown;
  }
}
