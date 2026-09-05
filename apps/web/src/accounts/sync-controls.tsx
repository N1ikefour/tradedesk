import { messageForError } from '@/api/error-message';
import { useSetAccountPaused, useSyncNow, type Account } from '@/accounts/api';
import { usesCollector } from '@/accounts/status';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { t } from '@/i18n';

/**
 * «Синхронизировать» — просьба, а не действие. `POST /sync-now` отвечает `202`: сделки
 * заберёт коллектор на очередном heartbeat, и в момент ответа синка ещё не было
 * (SPEC.md 5.2). Поэтому здесь нет ни одного исхода со словом «синхронизировано».
 *
 * Что именно сказать, решает сервер: в ответе приходит `collector_online` — его вердикт
 * по своему порогу. Второй копии порога на фронте нет намеренно, см. `describeHeartbeat`.
 */
export function SyncNowButton({ account }: { account: Account }) {
  const sync = useSyncNow(account.id);

  if (!usesCollector(account)) {
    return null;
  }

  const paused = account.status === 'paused';

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={sync.isPending || paused}
          onClick={() => sync.mutate()}
        >
          {sync.isPending ? t.accounts.syncing : t.accounts.sync}
        </Button>
        {paused ? (
          <span className="text-xs text-muted-foreground">{t.accounts.syncDisabledPaused}</span>
        ) : null}
      </div>

      {sync.isSuccess ? (
        <Alert variant={sync.data.collector_online ? 'default' : 'warning'}>
          {sync.data.collector_online ? t.accounts.syncQueuedOnline : t.accounts.syncQueuedOffline}
        </Alert>
      ) : null}

      {sync.isError ? (
        <Alert variant="destructive">
          {t.accounts.syncFailed} {messageForError(sync.error)}
        </Alert>
      ) : null}
    </div>
  );
}

/** Пауза и возобновление — одна кнопка: у счёта ровно два положения. */
export function PauseButton({ account }: { account: Account }) {
  const paused = account.status === 'paused';
  const setPaused = useSetAccountPaused(account.id);

  if (account.status === 'archived') {
    return null;
  }

  const pending = setPaused.isPending;
  const label = paused
    ? pending
      ? t.accounts.resuming
      : t.accounts.resume
    : pending
      ? t.accounts.pausing
      : t.accounts.pause;

  return (
    <div className="flex flex-col gap-2">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={pending}
        onClick={() => setPaused.mutate(!paused)}
      >
        {label}
      </Button>
      {setPaused.isError ? (
        <Alert variant="destructive">
          {t.accounts.pauseFailed} {messageForError(setPaused.error)}
        </Alert>
      ) : null}
    </div>
  );
}
