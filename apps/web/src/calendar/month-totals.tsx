/**
 * Итог месяца — SPEC.md 9.3, «итоги по месяцу сверху».
 *
 * Числа сложены на клиенте из дней ответа, и это законно ровно потому, что месяц пришёл
 * одним ответом целиком: сумма дней здесь — сумма всего множества, а не видимой части
 * (`calendar/totals.ts`). Деньги складываются `sumDecimals`, то есть на `BigInt`.
 *
 * Множество названо словами не для красоты: в календаре только закрытые позиции
 * (`docs/metrics.md` §5), и человек, сверяющий этот итог с журналом за месяц без фильтра
 * «Закрытые», получит другое число — но не потому, что кто-то ошибся.
 */
import { moneyView } from '@/calendar/day-view';
import type { CalendarTotals } from '@/calendar/totals';
import { t } from '@/i18n';
import { cn } from '@/lib/utils';

function Metric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn('text-sm font-medium tabular-nums', tone)}>{value}</dd>
    </div>
  );
}

export function MonthTotals({ totals }: { totals: CalendarTotals }) {
  const sum = totals.netPnl === null ? null : moneyView(totals.netPnl);
  return (
    <dl className="flex flex-wrap items-start gap-x-8 gap-y-3 rounded-lg border border-border p-4">
      <div className="flex flex-col gap-0.5">
        <dt className="text-xs text-muted-foreground">{t.calendar.monthTotal}</dt>
        <dd
          className={cn('text-xl font-semibold tabular-nums', sum?.tone ?? 'text-muted-foreground')}
        >
          {sum?.text ?? t.calendar.unknownValue}
        </dd>
      </div>
      <Metric label={t.calendar.monthTrades} value={String(totals.trades)} />
      <Metric label={t.calendar.monthWins} value={String(totals.wins)} />
      <Metric label={t.calendar.monthLosses} value={String(totals.losses)} />
      <Metric label={t.calendar.monthDays} value={String(totals.days)} />
    </dl>
  );
}
