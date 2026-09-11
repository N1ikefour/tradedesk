import { useState } from 'react';
import { useSearchParams } from 'react-router';

import { messageForError } from '@/api/error-message';
import { AccountCard } from '@/accounts/account-card';
import { AccountForm } from '@/accounts/account-form';
import { useAccounts } from '@/accounts/api';
import { CollectorBlock } from '@/accounts/collector-block';
import { QueryProgress } from '@/components/query-progress';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Modal } from '@/components/ui/modal';
import { t } from '@/i18n';
import { useNow } from '@/lib/use-now';

/** Относительное время в статусах не должно застывать на значении первого рендера. */
const CLOCK_TICK_MS = 30_000;

const ARCHIVED_PARAM = 'archived';

/** Экран счетов — SPEC.md 9.1 `/accounts`, содержимое 9.3. */
export function AccountsPage() {
  // Состояние списка живёт в адресе: после перезагрузки видно то же, что и до неё.
  const [params, setParams] = useSearchParams();
  const includeArchived = params.get(ARCHIVED_PARAM) === '1';
  const [creating, setCreating] = useState(false);
  const now = useNow(CLOCK_TICK_MS);

  const accounts = useAccounts(includeArchived);
  const items = accounts.data?.items ?? [];

  const toggleArchived = (checked: boolean) => {
    const next = new URLSearchParams(params);
    if (checked) {
      next.set(ARCHIVED_PARAM, '1');
    } else {
      next.delete(ARCHIVED_PARAM);
    }
    setParams(next, { replace: true });
  };

  return (
    <section className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{t.pages.accounts}</h1>
        <p className="text-sm text-muted-foreground">{t.accounts.hint}</p>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <Button type="button" onClick={() => setCreating(true)}>
          {t.accounts.add}
        </Button>
        <div className="flex items-center gap-2">
          <input
            id="accounts-show-archived"
            type="checkbox"
            className="size-4 accent-primary"
            checked={includeArchived}
            onChange={(event) => toggleArchived(event.target.checked)}
          />
          <Label htmlFor="accounts-show-archived">{t.accounts.showArchived}</Label>
        </div>
      </div>

      {accounts.isPending ? <QueryProgress fetchStatus={accounts.fetchStatus} /> : null}

      {accounts.isError ? (
        <div className="flex flex-col items-start gap-3">
          <Alert variant="destructive">
            {t.accounts.loadFailed} {messageForError(accounts.error)}
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

      {accounts.isSuccess && items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {includeArchived ? t.accounts.emptyArchived : t.accounts.empty}
        </p>
      ) : null}

      {items.length > 0 ? (
        <div className="flex flex-col gap-4">
          {items.map((account) => (
            <AccountCard key={account.id} account={account} now={now} />
          ))}
        </div>
      ) : null}

      <CollectorBlock />

      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title={t.accounts.formCreateTitle}
        className="max-w-xl"
      >
        {/* Форма пересоздаётся при каждом открытии: прошлый ввод не должен пережить
            закрытие окна. */}
        {creating ? (
          <AccountForm onDone={() => setCreating(false)} onCancel={() => setCreating(false)} />
        ) : null}
      </Modal>
    </section>
  );
}
