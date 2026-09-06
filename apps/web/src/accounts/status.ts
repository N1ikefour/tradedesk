/**
 * Как статус счёта (SPEC.md 9.3) выглядит на экране. Одно место на все карточки: цвет и
 * подпись, разъехавшиеся между списком и страницей счёта, читаются как разные состояния.
 */
import type { Account } from '@/accounts/api';
import { t } from '@/i18n';
import { formatRelativePast } from '@/lib/format';

export type StatusTone = 'neutral' | 'success' | 'warning' | 'destructive';

export type StatusView = {
  tone: StatusTone;
  label: string;
  detail: string;
};

export function describeStatus(account: Account, now: Date): StatusView {
  switch (account.status) {
    case 'connected':
      return {
        tone: 'success',
        label: t.accounts.statusConnected,
        detail:
          account.last_sync_at === null
            ? t.accounts.statusConnectedNever
            : t.accounts.statusConnectedHint(formatRelativePast(account.last_sync_at, now)),
      };
    case 'needs_attention':
      return {
        tone: 'destructive',
        label: t.accounts.statusNeedsAttention,
        // Текст пишет сервер (`check_collectors`, ингест). Пустым он приходить не должен,
        // но красный бейдж без причины — худшее, что можно показать в этом статусе.
        detail: account.status_message ?? t.accounts.statusNeedsAttentionFallback,
      };
    case 'paused':
      return {
        tone: 'neutral',
        label: t.accounts.statusPaused,
        detail: t.accounts.statusPausedHint,
      };
    case 'archived':
      return {
        tone: 'neutral',
        label: t.accounts.statusArchived,
        detail: t.accounts.statusArchivedHint,
      };
    case 'pending':
      return {
        tone: 'neutral',
        label: t.accounts.statusPending,
        detail: t.accounts.statusPendingHint,
      };
  }
}

/**
 * Сделки приносит коллектор, и только счетам MT5. У счёта «вручную» heartbeat не будет
 * никогда, и предупреждать о его отсутствии значило бы придумать несуществующую поломку.
 * Архивный счёт из работы выведен — коллектор его уже не видит (SPEC.md 5.6).
 */
export function usesCollector(account: Account): boolean {
  return account.platform === 'mt5' && account.status !== 'archived';
}

export type HeartbeatView = {
  text: string;
  /** Жёлтым — только то, что человек может исправить: коллектора ещё не было. */
  warn: boolean;
};

/**
 * Что известно о связи с коллектором **из списка счетов**. Порога «свежести» здесь нет:
 * он живёт на сервере (`COLLECTOR_OFFLINE_AFTER`) и приходит готовым вердиктом в ответе
 * `POST /sync-now` (`collector_online`). Своя копия числа разошлась бы с серверной молча,
 * а разошедшийся порог — это предупреждение, которое врёт в обе стороны.
 */
export function describeHeartbeat(account: Account, now: Date): HeartbeatView {
  if (account.last_heartbeat_at === null) {
    return { text: t.accounts.heartbeatNever, warn: true };
  }
  return {
    text: t.accounts.heartbeatLast(formatRelativePast(account.last_heartbeat_at, now)),
    warn: false,
  };
}

export function platformName(platform: Account['platform']): string {
  switch (platform) {
    case 'mt5':
      return t.accounts.platformMt5;
    case 'csv':
      return t.accounts.platformCsv;
    case 'manual':
      return t.accounts.platformManual;
  }
}
