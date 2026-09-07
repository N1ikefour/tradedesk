/**
 * Блок «Требует внимания» — SPEC.md 9.3: счета `needs_attention`, коллектор не на связи,
 * сделки без рефлексии.
 *
 * ⚠️ Порога «коллектор молчит» здесь нет и быть не должно (решение `S1-11`). Число пять
 * минут живёт на сервере в одном месте на трёх потребителей, и четвёртая копия разошлась
 * бы с ними молча — то есть предупреждение врало бы в обе стороны. Вердикт приходит
 * готовым: статус `needs_attention` ставит `check_collectors`. Единственный факт, который
 * фронт называет сам, порога не требует вовсе — связи не было **ни разу**.
 */
import type { Account } from '@/accounts/api';
import { usesCollector } from '@/accounts/status';
import { t } from '@/i18n';

export type AttentionTone = 'destructive' | 'warning';

export type AttentionItem = {
  readonly key: string;
  readonly tone: AttentionTone;
  /** Что случилось. Для `needs_attention` текст пишет сервер. */
  readonly title: string;
  readonly detail: string;
  readonly accountId: string;
  readonly accountLabel: string;
  readonly accountColor: string;
};

export function accountAttention(accounts: readonly Account[]): readonly AttentionItem[] {
  const items: AttentionItem[] = [];
  for (const account of accounts) {
    if (account.status === 'needs_attention') {
      items.push({
        key: `needs-attention:${account.id}`,
        tone: 'destructive',
        title: t.accounts.statusNeedsAttention,
        // Красный пункт без причины — худшее, что можно показать: сервер сообщение
        // присылает, но пустым оно приходить не должно, а не «не может».
        detail: account.status_message ?? t.dashboard.attentionNeedsAttentionFallback,
        accountId: account.id,
        accountLabel: account.label,
        accountColor: account.color,
      });
      continue;
    }
    // Счёт уже назван выше — второй строкой о том же счёте блок только шумел бы.
    if (usesCollector(account) && account.last_heartbeat_at === null) {
      items.push({
        key: `no-heartbeat:${account.id}`,
        tone: 'warning',
        title: t.accounts.heartbeatNever,
        detail: t.dashboard.attentionNoHeartbeatHint,
        accountId: account.id,
        accountLabel: account.label,
        accountColor: account.color,
      });
    }
  }
  return items;
}
