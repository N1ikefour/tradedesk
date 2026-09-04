import { describe, expect, it } from 'vitest';

import { messageForError } from '@/api/error-message';
import { ApiRequestError, NetworkError, toApiRequestError } from '@/api/errors';
import { t } from '@/i18n';

describe('разбор ошибки API', () => {
  it('читает формат SPEC.md 5.1', () => {
    const error = toApiRequestError(429, {
      error: { code: 'rate_limited', message: 'Слишком часто', details: { retry_after: 17 } },
    });

    expect(error.status).toBe(429);
    expect(error.code).toBe('rate_limited');
    expect(error.retryAfter).toBe(17);
  });

  it('дробный retry_after округляется вверх — «через 0 секунд» не показываем', () => {
    const error = toApiRequestError(429, {
      error: { code: 'rate_limited', message: '', details: { retry_after: 0.2 } },
    });
    expect(error.retryAfter).toBe(1);
  });

  it('тело не по контракту не роняет разбор', () => {
    const error = toApiRequestError(500, '<html>502 Bad Gateway</html>');
    expect(error.code).toBeNull();
    expect(error.retryAfter).toBeNull();
  });
});

describe('текст ошибки', () => {
  const cases: ReadonlyArray<[string, string]> = [
    ['invalid_code', t.errors.invalidCode],
    ['too_many_attempts', t.errors.tooManyAttempts],
    ['validation_error', t.errors.validation],
    ['unauthorized', t.errors.unauthorized],
    ['forbidden_origin', t.errors.forbiddenOrigin],
    ['not_found', t.errors.notFound],
    ['internal_error', t.errors.unknown],
  ];

  it.each(cases)('%s → свой текст', (code, expected) => {
    expect(messageForError(new ApiRequestError(400, code, '', {}))).toBe(expected);
  });

  it('invalid_code и too_many_attempts — разные состояния для пользователя', () => {
    expect(messageForError(new ApiRequestError(422, 'invalid_code', '', {}))).not.toBe(
      messageForError(new ApiRequestError(422, 'too_many_attempts', '', {})),
    );
  });

  it('rate_limited подставляет retry_after', () => {
    const error = new ApiRequestError(429, 'rate_limited', '', { retry_after: 5 });
    expect(messageForError(error)).toBe('Слишком много запросов. Повторите через 5 секунд.');
  });

  it('несостоявшийся запрос отличается от ответа с ошибкой', () => {
    expect(messageForError(new NetworkError(new Error('offline')))).toBe(t.errors.network);
  });
});
