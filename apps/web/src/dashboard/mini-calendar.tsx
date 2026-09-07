/**
 * Календарь-мини текущего месяца — SPEC.md 9.3.
 *
 * ⚠️ Границы дня приходят с сервера (`starts_at`/`ends_at`) и подставляются в журнал как
 * есть. Второй реализации правила торгового дня на клиенте нет: разойдясь, календарь
 * показал бы сделку в понедельник, а журнал за понедельник её не нашёл бы. Отсюда прямое
 * следствие: день, которого нет в ответе, ссылкой не становится — границ у него нет.
 */
import { Link } from 'react-router';

import type { CalendarMonth } from '@/dashboard/api';
import { BlockStatus, DashboardBlock, type BlockQueryState } from '@/dashboard/block';
import { buildMonthGrid, type CalendarCell } from '@/dashboard/calendar-grid';
import { journalDayLink } from '@/dashboard/period';
import { t } from '@/i18n';
import { pnlToneClass } from '@/journal/position-view';
import { decimalSign, formatMoney } from '@/lib/decimal';
import { cn } from '@/lib/utils';

const MONTH_INDEX_OFFSET = 1;

function monthTitle(month: string): string {
  const [year, index] = month.split('-');
  const monthIndex = Number(index) - MONTH_INDEX_OFFSET;
  if (year === undefined || !Number.isInteger(monthIndex)) {
    return month;
  }
  return t.dashboard.calendarMonth(monthIndex, Number(year));
}

function Cell({ cell, today }: { cell: CalendarCell; today: string }) {
  const isToday = cell.iso === today;
  const day = cell.day;
  const netPnl = day === null ? null : formatMoney(day.net_pnl);
  const sign = day === null ? null : decimalSign(day.net_pnl);

  const body = (
    <>
      <span
        className={cn(
          'text-[11px]',
          isToday ? 'font-semibold text-foreground' : 'text-muted-foreground',
        )}
      >
        {cell.dayOfMonth}
        {isToday ? <span className="sr-only"> ({t.dashboard.calendarToday})</span> : null}
      </span>
      {day === null ? null : (
        <>
          <span
            className={cn(
              'truncate text-xs font-medium tabular-nums',
              pnlToneClass(sign ?? 'zero'),
            )}
          >
            {netPnl ?? t.dashboard.unknownValue}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {t.dashboard.calendarTrades(day.trades)}
          </span>
        </>
      )}
    </>
  );

  const className = cn(
    'flex h-16 flex-col justify-start gap-0.5 rounded-md border p-1.5',
    isToday ? 'border-ring' : 'border-border',
  );

  if (day === null) {
    return <div className={cn(className, 'bg-muted/20')}>{body}</div>;
  }
  return (
    <Link
      to={journalDayLink(day.starts_at, day.ends_at)}
      aria-label={t.dashboard.calendarDayLabel(cell.dayOfMonth, day.trades, netPnl ?? day.net_pnl)}
      className={cn(className, 'hover:bg-accent/50')}
    >
      {body}
    </Link>
  );
}

export function MiniCalendar({
  query,
  month,
  today,
}: {
  query: BlockQueryState;
  month: CalendarMonth | undefined;
  today: string;
}) {
  const weeks = month === undefined ? [] : buildMonthGrid(month.month, month.days);

  return (
    <DashboardBlock
      title={month === undefined ? t.dashboard.calendarTitle : monthTitle(month.month)}
      hint={t.dashboard.calendarHint}
    >
      <BlockStatus query={query} failedMessage={t.dashboard.calendarFailed} />
      {month === undefined ? null : (
        <>
          {month.days.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t.dashboard.calendarEmpty}</p>
          ) : null}
          <div className="overflow-x-auto">
            <div className="min-w-[480px]">
              <div className="mb-1 grid grid-cols-7 gap-1">
                {t.dashboard.calendarWeekdays.map((weekday) => (
                  <span key={weekday} className="text-center text-[11px] text-muted-foreground">
                    {weekday}
                  </span>
                ))}
              </div>
              <div className="grid grid-cols-7 gap-1">
                {weeks.map((week, weekIndex) =>
                  week.map((cell, dayIndex) =>
                    cell === null ? (
                      <div key={`empty-${weekIndex}-${dayIndex}`} aria-hidden="true" />
                    ) : (
                      <Cell key={cell.iso} cell={cell} today={today} />
                    ),
                  ),
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </DashboardBlock>
  );
}
