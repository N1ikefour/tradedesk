/**
 * Строка журнала → то, что видно на экране. Один вид на две раскладки: таблицу и
 * мобильные карточки (SPEC.md 9.3). Форматирование живёт здесь, а не в разметке, — иначе
 * две раскладки начинают показывать одни и те же данные по-разному, и заметно это станет
 * только на чужом телефоне.
 */
import { t } from '@/i18n';
import type { PositionListItem } from '@/journal/api';
import {
  decimalSign,
  divideDecimal,
  formatMoney,
  formatPrice,
  formatRatio,
  formatVolume,
  type DecimalSign,
} from '@/lib/decimal';
import { formatDateTime, formatDuration } from '@/lib/format';

const RATIO_DIGITS = 2;

export type PositionView = {
  readonly id: string;
  readonly href: string;
  /** Подпись счёта для полоски цвета: сам цвет ничего не говорит скринридеру. */
  readonly accountTitle: string;
  readonly accountColor: string;
  readonly symbol: string;
  readonly direction: 'long' | 'short';
  readonly directionLabel: string;
  readonly isOpen: boolean;
  readonly openTime: string;
  readonly closeTime: string;
  readonly volume: string;
  readonly entryPrice: string;
  readonly exitPrice: string;
  readonly duration: string;
  readonly netPnl: string;
  readonly netPnlSign: DecimalSign;
  /** Отношение `net_pnl / risk_amount` (SPEC.md 9.3). Нет плана — нет и числа. */
  readonly ratio: string | null;
  readonly tags: readonly string[];
  readonly hasReflection: boolean;
  readonly hasAttachments: boolean;
};

function orDash(value: string | null): string {
  return value ?? t.journal.unknownValue;
}

function ratioOf(item: PositionListItem): string | null {
  const risk = item.journal_entry?.risk_amount;
  if (risk === null || risk === undefined) {
    return null;
  }
  const value = divideDecimal(item.net_pnl, risk, RATIO_DIGITS);
  return value === null ? null : formatRatio(value);
}

export function describePosition(item: PositionListItem, timeZone: string): PositionView {
  const isOpen = item.status === 'open';
  return {
    id: item.id,
    href: `/journal/${item.id}`,
    accountTitle: item.account.is_demo
      ? `${item.account.label} · ${t.journal.demoBadge}`
      : item.account.label,
    accountColor: item.account.color,
    symbol: item.symbol_norm,
    direction: item.direction,
    directionLabel: item.direction === 'long' ? t.journal.long : t.journal.short,
    isOpen,
    openTime: formatDateTime(item.open_time, timeZone),
    // У открытой позиции времени закрытия нет, и это не пропуск данных, а её состояние —
    // поэтому здесь слово, а не прочерк: прочерк читается как «не загрузилось».
    closeTime:
      item.close_time === null ? t.journal.stillOpen : formatDateTime(item.close_time, timeZone),
    volume: orDash(formatVolume(item.volume_opened)),
    entryPrice: orDash(formatPrice(item.avg_entry_price)),
    exitPrice:
      item.avg_exit_price === null
        ? t.journal.unknownValue
        : orDash(formatPrice(item.avg_exit_price)),
    duration:
      item.duration_seconds === null
        ? t.journal.unknownValue
        : formatDuration(item.duration_seconds),
    netPnl: orDash(formatMoney(item.net_pnl)),
    netPnlSign: decimalSign(item.net_pnl) ?? 'zero',
    ratio: ratioOf(item),
    tags: item.journal_entry?.tags ?? [],
    hasReflection: item.reflection?.filled_at != null,
    hasAttachments: item.attachments_count > 0,
  };
}

/** Класс цвета для P&L — SPEC.md 9.4: зелёный/красный/серый. */
export function pnlToneClass(sign: DecimalSign): string {
  switch (sign) {
    case 'positive':
      return 'text-success';
    case 'negative':
      return 'text-destructive';
    case 'zero':
      return 'text-muted-foreground';
  }
}
