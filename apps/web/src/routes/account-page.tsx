import { Link, useNavigate, useParams } from 'react-router';

import { messageForError } from '@/api/error-message';
import { AccountHeartbeat, AccountStatusLine } from '@/accounts/account-card';
import { AccountForm } from '@/accounts/account-form';
import { useAccounts, useSyncRuns, type Account, type SyncRun } from '@/accounts/api';
import { CollectorBlock } from '@/accounts/collector-block';
import { DangerActions } from '@/accounts/danger-actions';
import { PauseButton, SyncNowButton } from '@/accounts/sync-controls';
import { QueryProgress } from '@/components/query-progress';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { t } from '@/i18n';
import { formatDateTime } from '@/lib/format';
import { useNow } from '@/lib/use-now';
import { useProfileTimeZone } from '@/user/profile';

const CLOCK_TICK_MS = 30_000;

/**
 * Страница счёта — SPEC.md 9.1 `/accounts/:id`: настройки и история синков.
 *
 * Счёт читается из того же списка, что и на `/accounts`, — отдельного `GET /accounts/{id}`
 * в контракте нет. Архивные запрашиваются явно: иначе страница архивного счёта, открытая
 * по ссылке, показывала бы «такого счёта нет».
 */
export function AccountPage() {
  const { id } = useParams<'id'>();
  const navigate = useNavigate();
  const now = useNow(CLOCK_TICK_MS);
  const accounts = useAccounts(true);

  const account = accounts.data?.items.find((item) => item.id === id) ?? null;

  return (
    <section className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <Button asChild variant="link" size="sm" className="self-start px-0">
        <Link to="/accounts">{t.account.backToList}</Link>
      </Button>

      {accounts.isPending ? <QueryProgress fetchStatus={accounts.fetchStatus} /> : null}

      {accounts.isError ? (
        <div className="flex flex-col items-start gap-3">
          <Alert variant="destructive">
            {t.account.loadFailed} {messageForError(accounts.error)}
          </Alert>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={accounts.isFetching}
            onClick={() => {
              void accounts.refetch();
            }}
          >
            {t.common.retry}
          </Button>
        </div>
      ) : null}

      {accounts.isSuccess && account === null ? <Alert>{t.account.notFound}</Alert> : null}

      {account === null ? null : (
        <AccountDetails
          account={account}
          now={now}
          onDeleted={() => {
            void navigate('/accounts', { replace: true });
          }}
        />
      )}
    </section>
  );
}

function AccountDetails({
  account,
  now,
  onDeleted,
}: {
  account: Account;
  now: Date;
  onDeleted: () => void;
}) {
  return (
    <>
      <Card className="flex overflow-hidden">
        <div
          aria-hidden="true"
          style={{ backgroundColor: account.color }}
          className="w-1.5 shrink-0"
        />
        <CardContent className="flex min-w-0 flex-1 flex-col gap-4 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold tracking-tight">{account.label}</h1>
              {account.is_demo ? <Badge>{t.accounts.demoBadge}</Badge> : null}
            </div>
            <AccountStatusLine account={account} now={now} />
          </div>

          <p className="text-xs text-muted-foreground">
            {t.accounts.positionsCount(account.positions_count)}
          </p>

          <AccountHeartbeat account={account} now={now} />

          <div className="flex flex-wrap items-start gap-2">
            <SyncNowButton account={account} />
            <PauseButton account={account} />
            <DangerActions account={account} onDeleted={onDeleted} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-col gap-4 p-5">
          <h2 className="text-sm font-medium">{t.account.settingsTitle}</h2>
          {account.status === 'archived' ? (
            <Alert>{t.account.settingsArchived}</Alert>
          ) : (
            /* Форма пересоздаётся под другой счёт: чужие значения в полях недопустимы. */
            <AccountForm key={account.id} account={account} />
          )}
        </CardContent>
      </Card>

      <CollectorBlock />

      <SyncRunsTable accountId={account.id} />
    </>
  );
}

/** Чем закончился прогон: `finished_at` пуст — идёт, `error` заполнен — упал. */
function runOutcome(run: SyncRun): { label: string; tone: 'neutral' | 'success' | 'destructive' } {
  if (run.error !== null) {
    return { label: t.account.runFailed, tone: 'destructive' };
  }
  if (run.finished_at === null) {
    return { label: t.account.runRunning, tone: 'neutral' };
  }
  return { label: t.account.runOk, tone: 'success' };
}

function numberOrDash(value: number | null): string {
  return value === null ? t.account.unknownValue : String(value);
}

function SyncRunsTable({ accountId }: { accountId: string }) {
  const runs = useSyncRuns(accountId);
  const timeZone = useProfileTimeZone();
  const items = runs.data?.items ?? [];

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-5">
        <div className="flex flex-col gap-1">
          <h2 className="text-sm font-medium">{t.account.syncRunsTitle}</h2>
          <p className="text-xs text-muted-foreground">{t.account.syncRunsHint}</p>
        </div>

        {runs.isPending ? <QueryProgress fetchStatus={runs.fetchStatus} /> : null}

        {runs.isError ? (
          <div className="flex flex-col items-start gap-3">
            <Alert variant="destructive">
              {t.account.syncRunsFailed} {messageForError(runs.error)}
            </Alert>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={runs.isFetching}
              onClick={() => {
                void runs.refetch();
              }}
            >
              {t.common.retry}
            </Button>
          </div>
        ) : null}

        {runs.isSuccess && items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t.account.syncRunsEmpty}</p>
        ) : null}

        {items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th scope="col" className="py-2 pr-4 font-medium">
                    {t.account.columnStartedAt}
                  </th>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    {t.account.columnSource}
                  </th>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    {t.account.columnDealsReceived}
                  </th>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    {t.account.columnDealsNew}
                  </th>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    {t.account.columnPositionsRebuilt}
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    {t.account.columnResult}
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((run) => {
                  const outcome = runOutcome(run);
                  return (
                    <tr key={run.id} className="border-t border-border">
                      <td className="py-2 pr-4 whitespace-nowrap">
                        {formatDateTime(run.started_at, timeZone)}
                      </td>
                      <td className="py-2 pr-4">{run.source}</td>
                      <td className="py-2 pr-4">{numberOrDash(run.deals_received)}</td>
                      <td className="py-2 pr-4">{numberOrDash(run.deals_new)}</td>
                      <td className="py-2 pr-4">{numberOrDash(run.positions_rebuilt)}</td>
                      <td className="py-2">
                        <Badge tone={outcome.tone}>{outcome.label}</Badge>
                        {/* Текст ошибки пишет коллектор: он и есть единственное объяснение,
                            почему сделки не пришли. */}
                        {run.error === null ? null : (
                          <p className="mt-1 text-xs text-destructive">{run.error}</p>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
