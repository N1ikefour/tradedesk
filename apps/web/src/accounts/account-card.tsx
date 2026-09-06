import { Link } from 'react-router';

import type { Account } from '@/accounts/api';
import { DangerActions } from '@/accounts/danger-actions';
import { describeHeartbeat, describeStatus, platformName, usesCollector } from '@/accounts/status';
import { PauseButton, SyncNowButton } from '@/accounts/sync-controls';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { t } from '@/i18n';

/** Строка «брокер · сервер · счёт»: у счёта «вручную» её нет вовсе, а не пустая. */
function AccountIdentity({ account }: { account: Account }) {
  const server =
    account.server === null || account.login === null
      ? null
      : t.accounts.serverLine(account.server, account.login);

  return (
    <p className="text-sm text-muted-foreground">
      {[platformName(account.platform), account.broker ?? t.accounts.noBroker, server]
        .filter((part): part is string => part !== null)
        .join(' · ')}
    </p>
  );
}

export function AccountHeartbeat({ account, now }: { account: Account; now: Date }) {
  if (!usesCollector(account)) {
    return null;
  }
  const heartbeat = describeHeartbeat(account, now);
  return heartbeat.warn ? (
    <Alert variant="warning">{heartbeat.text}</Alert>
  ) : (
    <p className="text-xs text-muted-foreground">{heartbeat.text}</p>
  );
}

export function AccountStatusLine({ account, now }: { account: Account; now: Date }) {
  const status = describeStatus(account, now);
  return (
    <div className="flex flex-col gap-1">
      <Badge tone={status.tone}>{status.label}</Badge>
      <p className="text-sm text-muted-foreground">{status.detail}</p>
    </div>
  );
}

/**
 * Карточка счёта из SPEC.md 9.3. Цветная полоса — тот же цвет, которым счёт помечен в
 * журнале и календаре: он и есть способ узнать счёт, когда их несколько.
 */
export function AccountCard({ account, now }: { account: Account; now: Date }) {
  return (
    <Card className="flex overflow-hidden">
      <div
        aria-hidden="true"
        style={{ backgroundColor: account.color }}
        className="w-1.5 shrink-0"
      />
      <CardContent className="flex min-w-0 flex-1 flex-col gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold">{account.label}</h2>
              {account.is_demo ? <Badge>{t.accounts.demoBadge}</Badge> : null}
            </div>
            <AccountIdentity account={account} />
            <p className="text-xs text-muted-foreground">
              {t.accounts.positionsCount(account.positions_count)}
            </p>
          </div>
          <AccountStatusLine account={account} now={now} />
        </div>

        <AccountHeartbeat account={account} now={now} />

        <div className="flex flex-wrap items-start gap-2">
          <SyncNowButton account={account} />
          <PauseButton account={account} />
          <Button asChild variant="ghost" size="sm">
            <Link to={`/accounts/${account.id}`} title={t.accounts.openCard}>
              {t.accounts.edit}
            </Link>
          </Button>
          <DangerActions account={account} />
        </div>
      </CardContent>
    </Card>
  );
}
