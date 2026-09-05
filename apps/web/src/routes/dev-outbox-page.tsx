import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';

import { api, unwrap } from '@/api/client';
import { messageForError } from '@/api/error-message';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { t } from '@/i18n';
import { formatDateTime } from '@/lib/format';
import { useUserTimeZone } from '@/user/profile';

const OUTBOX_LIMIT = 50;

/**
 * Локальная почта (SPEC.md 9.1). Маршрут регистрируется только там, где эндпоинт есть,
 * — см. `DEV_OUTBOX_AVAILABLE`. Страница доступна без входа: код из письма нужен
 * именно тому, кто ещё не вошёл.
 */
export function DevOutboxPage() {
  // Своего запроса профиля страница не делает: она открыта и до входа (см. тест).
  // Если сессия уже в кэше, даты идут в зоне пользователя, иначе — в зоне компьютера.
  const timeZone = useUserTimeZone();
  const outbox = useQuery({
    queryKey: ['dev', 'outbox', OUTBOX_LIMIT],
    queryFn: () =>
      unwrap(api.GET('/api/v1/dev/outbox', { params: { query: { limit: OUTBOX_LIMIT } } })),
    refetchInterval: 5000,
  });

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-10">
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{t.outbox.title}</h1>
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void outbox.refetch();
            }}
            disabled={outbox.isFetching}
          >
            {t.outbox.refresh}
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link to="/login">{t.outbox.backToLogin}</Link>
          </Button>
        </div>
      </div>

      <p className="mb-6 text-sm text-muted-foreground">{t.outbox.hint}</p>

      {outbox.isPending ? (
        <p className="text-sm text-muted-foreground">{t.common.loading}</p>
      ) : null}

      {outbox.isError ? (
        <Alert variant="destructive">
          {t.outbox.loadFailed} {messageForError(outbox.error)}
        </Alert>
      ) : null}

      {outbox.data && outbox.data.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t.outbox.empty}</p>
      ) : null}

      <ul className="flex flex-col gap-4">
        {outbox.data?.items.map((item) => (
          <li key={item.id}>
            <Card>
              <CardHeader className="gap-1 pb-3">
                <CardTitle className="text-base">{item.subject}</CardTitle>
                <p className="text-xs text-muted-foreground">
                  {t.outbox.columnTo}: {item.to_email} · {t.outbox.columnCreatedAt}:{' '}
                  {formatDateTime(item.created_at, timeZone)}
                </p>
              </CardHeader>
              <CardContent>
                <pre className="overflow-x-auto rounded-md bg-muted p-3 text-sm whitespace-pre-wrap">
                  {item.body_text}
                </pre>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  );
}
