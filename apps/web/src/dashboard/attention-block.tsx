/**
 * «Требует внимания» — SPEC.md 9.3: счета `needs_attention`, коллектор не выходил на
 * связь, сделки без рефлексии.
 *
 * Число сделок без рефлексии называется точным только тогда, когда сервер сказал, что
 * продолжения нет (`next_cursor === null`). Иначе на экране «больше 20»: общего числа
 * строк список не отдаёт, и выдать длину первой страницы за итог значило бы напечатать
 * неправду ровно там, где человек ждёт факта.
 */
import { Link } from 'react-router';

import type { Account } from '@/accounts/api';
import type { CountProbe } from '@/dashboard/api';
import { UNREFLECTED_PROBE_LIMIT } from '@/dashboard/api';
import { accountAttention, type AttentionItem } from '@/dashboard/attention';
import { BlockStatus, DashboardBlock, type BlockQueryState } from '@/dashboard/block';
import { journalUnreflectedLink } from '@/dashboard/period';
import { Button } from '@/components/ui/button';
import { t } from '@/i18n';
import { cn } from '@/lib/utils';

function Item({ item }: { item: AttentionItem }) {
  return (
    <li className="flex flex-col items-start gap-1 border-t border-border pt-3 first:border-t-0 first:pt-0">
      <span className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="size-2 shrink-0 rounded-full"
          style={{ backgroundColor: item.accountColor }}
        />
        <span className="text-sm font-medium">{item.accountLabel}</span>
        <span
          className={cn(
            'text-sm',
            item.tone === 'destructive' ? 'text-destructive' : 'text-warning',
          )}
        >
          {item.title}
        </span>
      </span>
      <p className="text-xs text-muted-foreground">{item.detail}</p>
      <Button type="button" variant="link" size="sm" className="h-auto p-0" asChild>
        <Link to={`/accounts/${item.accountId}`}>{t.dashboard.attentionAccountLink}</Link>
      </Button>
    </li>
  );
}

export function AttentionBlock({
  accounts,
  unreflected,
  unreflectedQuery,
}: {
  accounts: readonly Account[];
  unreflected: CountProbe | undefined;
  unreflectedQuery: BlockQueryState;
}) {
  const items = accountAttention(accounts);
  const hasUnreflected = unreflected !== undefined && unreflected.count > 0;
  const empty = items.length === 0 && unreflected !== undefined && !hasUnreflected;

  return (
    <DashboardBlock title={t.dashboard.attentionTitle}>
      <BlockStatus query={unreflectedQuery} failedMessage={t.dashboard.attentionFailed} />
      {items.length === 0 ? null : (
        <ul className="flex flex-col gap-3">
          {items.map((item) => (
            <Item key={item.key} item={item} />
          ))}
        </ul>
      )}
      {hasUnreflected && unreflected !== undefined ? (
        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-3 first:border-t-0 first:pt-0">
          <span className="text-sm">
            {unreflected.exact
              ? t.dashboard.attentionUnreflected(unreflected.count)
              : t.dashboard.attentionUnreflectedMany(UNREFLECTED_PROBE_LIMIT)}
          </span>
          <Button type="button" variant="outline" size="sm" asChild>
            <Link to={journalUnreflectedLink()}>{t.dashboard.attentionUnreflectedLink}</Link>
          </Button>
        </div>
      ) : null}
      {empty ? <p className="text-sm text-muted-foreground">{t.dashboard.attentionEmpty}</p> : null}
    </DashboardBlock>
  );
}
