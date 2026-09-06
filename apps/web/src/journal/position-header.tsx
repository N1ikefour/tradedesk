/**
 * Шапка карточки — SPEC.md 9.3: символ, направление, счёт, статус, net P&L крупно,
 * gross/commission/swap мелко.
 *
 * Все числа печатает `@/lib/decimal`: в карточке они те же, что в строке журнала, и
 * второй способ округления развёл бы их между собой на глазах у человека.
 */
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { t } from '@/i18n';
import type { PositionCard } from '@/journal/api';
import { dictionaryLabel, pnlToneClass } from '@/journal/position-view';
import { decimalSign, formatMoney, formatPrice, formatVolume } from '@/lib/decimal';
import { formatDateTime, formatDuration } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useProfileTimeZone } from '@/user/profile';

function money(raw: string): string {
  return formatMoney(raw) ?? t.position.unknownValue;
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm tabular-nums">{value}</dd>
    </div>
  );
}

export function PositionHeader({
  position,
  headingLevel: Heading = 'h1',
}: {
  position: PositionCard;
  /** В модальном окне заголовок окна уже h2, и h1 внутри него ломал бы порядок. */
  headingLevel?: 'h1' | 'h2';
}) {
  const timeZone = useProfileTimeZone();
  const isOpen = position.status === 'open';
  const netSign = decimalSign(position.net_pnl) ?? 'zero';

  return (
    <Card className="flex overflow-hidden">
      <div
        aria-hidden="true"
        style={{ backgroundColor: position.account.color }}
        className="w-1.5 shrink-0"
      />
      <CardContent className="flex min-w-0 flex-1 flex-col gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            <div className="flex flex-wrap items-center gap-2">
              <Heading className="text-xl font-semibold tracking-tight">
                {position.symbol_norm}
              </Heading>
              <Badge>{position.direction === 'long' ? t.position.long : t.position.short}</Badge>
              {isOpen ? <Badge tone="warning">{t.position.openBadge}</Badge> : null}
              {position.is_manual ? <Badge>{t.position.manualBadge}</Badge> : null}
            </div>
            <p className="text-xs text-muted-foreground">
              {position.account.label}
              {position.account.is_demo ? ` · ${t.position.demoBadge}` : ''} ·{' '}
              {t.position.symbolRaw(position.symbol_raw)} ·{' '}
              {t.position.positionId(position.position_id)}
            </p>
          </div>

          <div className="flex flex-col items-end gap-1">
            <span className={cn('text-2xl font-semibold tabular-nums', pnlToneClass(netSign))}>
              {money(position.net_pnl)}
            </span>
            <span className="text-xs text-muted-foreground tabular-nums">
              {t.position.grossPnl} {money(position.gross_pnl)} · {t.position.commission}{' '}
              {money(position.commission)} · {t.position.swap} {money(position.swap)} ·{' '}
              {t.position.fee} {money(position.fee)}
            </span>
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Fact label={t.position.openedAt} value={formatDateTime(position.open_time, timeZone)} />
          <Fact
            label={t.position.closedAt}
            value={
              position.close_time === null
                ? t.position.stillOpen
                : formatDateTime(position.close_time, timeZone)
            }
          />
          <Fact
            label={t.position.duration}
            value={
              position.duration_seconds === null
                ? t.position.unknownValue
                : formatDuration(position.duration_seconds)
            }
          />
          <Fact
            label={t.position.volume}
            value={formatVolume(position.volume_opened) ?? t.position.unknownValue}
          />
          <Fact
            label={t.position.prices}
            value={`${formatPrice(position.avg_entry_price) ?? t.position.unknownValue} → ${
              position.avg_exit_price === null
                ? t.position.unknownValue
                : (formatPrice(position.avg_exit_price) ?? t.position.unknownValue)
            }`}
          />
          <Fact
            label={t.position.closeReason}
            value={dictionaryLabel(t.position.dealReasons, position.close_reason)}
          />
        </dl>
      </CardContent>
    </Card>
  );
}
