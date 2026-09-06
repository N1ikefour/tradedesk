/**
 * Код ошибки → текст для человека. Одно место на приложение: иначе один и тот же код
 * объясняется на разных экранах по-разному.
 */
import { ApiRequestError, ERROR_CODE, NetworkError } from '@/api/errors';
import { t } from '@/i18n';

export function messageForError(error: unknown): string {
  if (error instanceof NetworkError) {
    return error.timedOut ? t.errors.timeout : t.errors.network;
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
    case ERROR_CODE.positionNotFound:
      return t.errors.positionNotFound;
    case ERROR_CODE.accountNotFound:
      return t.errors.accountNotFound;
    case ERROR_CODE.accountAlreadyExists:
      return t.errors.accountAlreadyExists;
    case ERROR_CODE.accountArchived:
      return t.errors.accountArchived;
    case ERROR_CODE.accountPaused:
      return t.errors.accountPaused;
    case ERROR_CODE.notMt5Account:
      return t.errors.notMt5Account;
    default:
      return t.errors.unknown;
  }
}
