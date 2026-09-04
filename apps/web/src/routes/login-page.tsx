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

function redirectTarget(state: unknown): string {
  if (typeof state === 'object' && state !== null && 'from' in state) {
    const from = (state as { from: unknown }).from;
    // Только внутренний путь: значение приходит из истории навигации, и открытый
    // редирект на чужой адрес отсюда сделать нельзя.
    if (typeof from === 'string' && from.startsWith('/') && !from.startsWith('//')) {
      return from;
    }
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
  const [retrySeconds, setRetrySeconds] = useState<number | null>(null);

  // Отметку ставит обработчик 401 (auth/session.ts). Читается один раз при входе
  // на страницу и сразу снимается, чтобы не всплыть при следующем визите.
  const [sessionExpired] = useState(
    () => queryClient.getQueryData<boolean>(SESSION_EXPIRED_QUERY_KEY) === true,
  );
  useEffect(() => {
    queryClient.removeQueries({ queryKey: SESSION_EXPIRED_QUERY_KEY });
  }, [queryClient]);

  useEffect(() => {
    if (retrySeconds === null) {
      return;
    }
    if (retrySeconds <= 0) {
      setRetrySeconds(null);
      setError(null);
      return;
    }
    const timer = window.setTimeout(() => {
      setRetrySeconds(retrySeconds - 1);
    }, 1000);
    return () => {
      window.clearTimeout(timer);
    };
  }, [retrySeconds]);

  const handleFailure = (cause: unknown) => {
    setError(cause);
    if (cause instanceof ApiRequestError && cause.code === ERROR_CODE.rateLimited) {
      setRetrySeconds(cause.retryAfter);
    }
  };

  const sendCode = (target: string) => {
    setError(null);
    requestCode.mutate(target, {
      onSuccess: () => {
        setCode('');
        setStep('code');
      },
      onError: handleFailure,
    });
  };

  const handleEmailSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = email.trim();
    if (value.length === 0 || requestCode.isPending || retrySeconds !== null) {
      return;
    }
    sendCode(value);
  };

  const submitCode = (value: string) => {
    if (verifyCode.isPending) {
      return;
    }
    setError(null);
    verifyCode.mutate(
      { email: email.trim(), code: value },
      {
        onSuccess: () => {
          void navigate(redirectTarget(location.state), { replace: true });
        },
        onError: (cause) => {
          setCode('');
          handleFailure(cause);
        },
      },
    );
  };

  const handleCodeChange = (event: ChangeEvent<HTMLInputElement>) => {
    const digits = event.target.value.replace(/\D/g, '').slice(0, CODE_LENGTH);
    setCode(digits);
    setError(null);
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

  // Вошедшему на /login делать нечего: уводим туда, откуда пришёл.
  if (session.data) {
    return <Navigate to={redirectTarget(location.state)} replace />;
  }

  const errorText =
    retrySeconds !== null
      ? t.errors.rateLimited(retrySeconds)
      : error !== null
        ? messageForError(error)
        : null;

  const blockedByRateLimit = retrySeconds !== null;

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
          {sessionExpired ? <Alert>{t.login.sessionExpired}</Alert> : null}
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
                  onChange={(event) => {
                    setEmail(event.target.value);
                  }}
                  disabled={requestCode.isPending}
                />
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
                  onChange={handleCodeChange}
                  disabled={verifyCode.isPending}
                />
              </div>
              <Button type="submit" disabled={verifyCode.isPending || code.length !== CODE_LENGTH}>
                {verifyCode.isPending ? t.login.verifying : t.login.submit}
              </Button>
              <div className="flex items-center justify-between text-sm">
                <button
                  type="button"
                  className="text-muted-foreground underline-offset-4 hover:underline"
                  onClick={() => {
                    setStep('email');
                    setCode('');
                    setError(null);
                  }}
                >
                  {t.login.changeEmail}
                </button>
                <button
                  type="button"
                  className="text-primary underline-offset-4 hover:underline disabled:opacity-50"
                  disabled={requestCode.isPending || blockedByRateLimit}
                  onClick={() => {
                    sendCode(email.trim());
                  }}
                >
                  {t.login.resend}
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
