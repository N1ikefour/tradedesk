import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router';

import { messageForError } from '@/api/error-message';
import { ApiRequestError, ERROR_CODE } from '@/api/errors';
import {
  SESSION_EXPIRED_QUERY_KEY,
  useRequestCode,
  useSession,
  useVerifyCode,
} from '@/auth/session';
import { ThemeToggle } from '@/components/theme-toggle';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { t } from '@/i18n';
import { DEV_OUTBOX_AVAILABLE } from '@/lib/env';

/** Длина кода — SPEC.md 4; при шестой цифре форма отправляется сама (SPEC.md 9.3). */
const CODE_LENGTH = 6;

/** Лимит на запрос кода считается по адресу (SPEC.md 4), поэтому и блокировка — по адресу. */
type RateLimit = { email: string; seconds: number | null };

function readState(state: unknown, key: string): string | null {
  if (typeof state === 'object' && state !== null && key in state) {
    const value = (state as Record<string, unknown>)[key];
    return typeof value === 'string' ? value : null;
  }
  return null;
}

function redirectTarget(state: unknown): string {
  const from = readState(state, 'from');
  // Только внутренний путь: значение приходит из истории навигации, и открытый
  // редирект на чужой адрес отсюда сделать нельзя.
  if (from !== null && from.startsWith('/') && !from.startsWith('//')) {
    return from;
  }
  return '/';
}

export function LoginPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const session = useSession();
  const requestCode = useRequestCode();
  const verifyCode = useVerifyCode();

  const [step, setStep] = useState<'email' | 'code'>('email');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [rateLimit, setRateLimit] = useState<RateLimit | null>(null);

  // Отметку ставит обработчик 401 (auth/session.ts). Читается один раз при входе
  // на страницу и сразу снимается, чтобы не всплыть при следующем визите.
  const [sessionExpired] = useState(
    () => queryClient.getQueryData<boolean>(SESSION_EXPIRED_QUERY_KEY) === true,
  );
  useEffect(() => {
    queryClient.removeQueries({ queryKey: SESSION_EXPIRED_QUERY_KEY });
  }, [queryClient]);

  const seconds = rateLimit?.seconds ?? null;
  useEffect(() => {
    if (seconds === null) {
      return;
    }
    if (seconds <= 0) {
      setRateLimit(null);
      return;
    }
    const timer = window.setTimeout(() => {
      setRateLimit((current) =>
        current === null || current.seconds === null
          ? current
          : { ...current, seconds: current.seconds - 1 },
      );
    }, 1000);
    return () => {
      window.clearTimeout(timer);
    };
  }, [seconds]);

  const normalizedEmail = email.trim().toLowerCase();
  // Блокирует только тот адрес, который упёрся в лимит: самый вероятный путь сюда —
  // опечатка в адресе, и человек должен иметь возможность её исправить сразу.
  const activeLimit = rateLimit !== null && rateLimit.email === normalizedEmail ? rateLimit : null;
  const blockedByRateLimit = activeLimit !== null && activeLimit.seconds !== null;

  const handleFailure = (target: string, cause: unknown) => {
    setNotice(null);
    if (cause instanceof ApiRequestError && cause.code === ERROR_CODE.rateLimited) {
      setError(null);
      setRateLimit({ email: target.toLowerCase(), seconds: cause.retryAfter });
      return;
    }
    setError(cause);
  };

  const sendCode = (target: string, resend: boolean) => {
    setError(null);
    setNotice(null);
    requestCode.mutate(target, {
      onSuccess: () => {
        setCode('');
        setStep('code');
        if (resend) {
          setNotice(t.login.codeResent(target));
        }
      },
      onError: (cause) => {
        handleFailure(target, cause);
      },
    });
  };

  const handleEmailSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = email.trim();
    if (value.length === 0 || requestCode.isPending || blockedByRateLimit) {
      return;
    }
    sendCode(value, false);
  };

  const submitCode = (value: string) => {
    if (verifyCode.isPending) {
      return;
    }
    const target = email.trim();
    setError(null);
    setNotice(null);
    verifyCode.mutate(
      { email: target, code: value },
      {
        onSuccess: () => {
          void navigate(redirectTarget(location.state), { replace: true });
        },
        onError: (cause) => {
          setCode('');
          handleFailure(target, cause);
        },
      },
    );
  };

  const handleCodeChange = (event: ChangeEvent<HTMLInputElement>) => {
    const digits = event.target.value.replace(/\D/g, '').slice(0, CODE_LENGTH);
    setCode(digits);
    setError(null);
    setNotice(null);
    if (digits.length === CODE_LENGTH) {
      submitCode(digits);
    }
  };

  const handleCodeSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (code.length === CODE_LENGTH) {
      submitCode(code);
    }
  };

  const backToEmail = () => {
    setStep('email');
    setCode('');
    setError(null);
    setNotice(null);
  };

  // Вошедшему на /login делать нечего: уводим туда, откуда пришёл.
  if (session.data) {
    return <Navigate to={redirectTarget(location.state)} replace />;
  }

  const apiError = error instanceof ApiRequestError ? error : null;
  const validationError = apiError?.code === ERROR_CODE.validation ? apiError : null;
  const emailFieldError = validationError?.fieldError('email') ?? null;
  const codeFieldError = validationError?.fieldError('code') ?? null;
  // Сообщение поля показывается у самого поля; общий алерт в этом случае — шум.
  const shownFieldError = step === 'email' ? emailFieldError : codeFieldError;

  const errorText =
    activeLimit !== null
      ? activeLimit.seconds === null
        ? t.errors.rateLimitedUnknownDelayFor(activeLimit.email)
        : t.errors.rateLimitedFor(activeLimit.email, activeLimit.seconds)
      : error !== null && shownFieldError === null
        ? messageForError(error)
        : null;

  const noticeText =
    notice ??
    (readState(location.state, 'reason') === 'check-failed'
      ? t.login.sessionCheckFailed
      : sessionExpired
        ? t.login.sessionExpired
        : null);

  return (
    <div className="relative flex min-h-screen items-center justify-center px-4 py-10">
      {/* Шапки на /login нет, а переключатель темы нужен и до входа. */}
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{t.login.title}</CardTitle>
          <CardDescription>
            {step === 'email' ? t.login.emailStepHint : t.login.codeStepHint(email.trim())}
          </CardDescription>
        </CardHeader>

        <CardContent className="flex flex-col gap-4">
          {noticeText === null ? null : <Alert>{noticeText}</Alert>}
          {errorText === null ? null : <Alert variant="destructive">{errorText}</Alert>}

          {step === 'email' ? (
            <form className="flex flex-col gap-4" onSubmit={handleEmailSubmit} noValidate>
              <div className="flex flex-col gap-2">
                <Label htmlFor="login-email">{t.login.emailLabel}</Label>
                <Input
                  id="login-email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  autoFocus
                  required
                  placeholder={t.login.emailPlaceholder}
                  value={email}
                  aria-invalid={emailFieldError !== null}
                  aria-describedby={emailFieldError === null ? undefined : 'login-email-error'}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    setError(null);
                    setNotice(null);
                  }}
                  disabled={requestCode.isPending}
                />
                {emailFieldError === null ? null : (
                  <p id="login-email-error" className="text-sm text-destructive">
                    {emailFieldError}
                  </p>
                )}
              </div>
              <Button
                type="submit"
                disabled={requestCode.isPending || blockedByRateLimit || email.trim().length === 0}
              >
                {requestCode.isPending ? t.login.requestingCode : t.login.requestCode}
              </Button>
            </form>
          ) : (
            <form className="flex flex-col gap-4" onSubmit={handleCodeSubmit} noValidate>
              <div className="flex flex-col gap-2">
                <Label htmlFor="login-code">{t.login.codeLabel}</Label>
                <Input
                  id="login-code"
                  name="code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  autoFocus
                  required
                  maxLength={CODE_LENGTH}
                  placeholder={t.login.codePlaceholder}
                  className="text-center text-lg tracking-[0.4em]"
                  value={code}
                  aria-invalid={codeFieldError !== null}
                  aria-describedby={codeFieldError === null ? undefined : 'login-code-error'}
                  onChange={handleCodeChange}
                  disabled={verifyCode.isPending}
                />
                {codeFieldError === null ? null : (
                  <p id="login-code-error" className="text-sm text-destructive">
                    {codeFieldError}
                  </p>
                )}
              </div>
              <Button type="submit" disabled={verifyCode.isPending || code.length !== CODE_LENGTH}>
                {verifyCode.isPending ? t.login.verifying : t.login.submit}
              </Button>
              <div className="flex items-center justify-between text-sm">
                <button
                  type="button"
                  className="text-muted-foreground underline-offset-4 hover:underline"
                  onClick={backToEmail}
                >
                  {t.login.changeEmail}
                </button>
                <button
                  type="button"
                  className="text-primary underline-offset-4 hover:underline disabled:opacity-50"
                  disabled={requestCode.isPending || blockedByRateLimit}
                  onClick={() => {
                    sendCode(email.trim(), true);
                  }}
                >
                  {requestCode.isPending ? t.login.requestingCode : t.login.resend}
                </button>
              </div>
            </form>
          )}

          {DEV_OUTBOX_AVAILABLE ? (
            <Link
              to="/dev/outbox"
              className="text-sm text-muted-foreground underline-offset-4 hover:underline"
            >
              {t.login.devOutboxLink}
            </Link>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
