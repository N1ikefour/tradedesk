/**
 * Календарь-мини текущего месяца — SPEC.md 9.3.
 *
 * ⚠️ Границы дня приходят с сервера (`starts_at`/`ends_at`) и подставляются в журнал как
 * есть. Второй реализации правила торгового дня на клиенте нет: разойдясь, календарь
 * показал бы сделку в понедельник, а журнал за понедельник её не нашёл бы. Отсюда прямое
 * следствие: день, которого нет в ответе, ссылкой не становится — границ у него нет.
 *
 * Раскладок две, и это не украшение. В сетке из семи колонок ячейка на телефоне шириной
 * около 50 px, а `-1 779,72 $` требует полутора таких: сумма обрезалась бы, а обрезанные
 * деньги хуже отсутствующих — их читают как другое число. Горизонтальная прокрутка тут не
 * лечит (месяц перестаёт быть виден целиком), поэтому ниже 768 px — той же границы, что у
 * журнала (SPEC.md 9.3), — месяц показывается списком торговых дней во всю ширину строки.
 * Дни, ссылки и суммы в обеих раскладках одни и те же, считаны одним `buildMonthGrid`.
 */
import { Link } from 'react-router';

import type { CalendarDay, CalendarMonth } from '@/dashboard/api';
import { BlockStatus, DashboardBlock, type BlockQueryState } from '@/dashboard/block';
import {
  buildMonthGrid,
  tradedCells,
  type CalendarCell,
  type CalendarWeek,
  type TradedCell,
} from '@/dashboard/calendar-grid';
import { journalDayLink } from '@/dashboard/period';
import { t } from '@/i18n';
import { pnlToneClass } from '@/journal/position-view';
import { decimalSign, formatMoney } from '@/lib/decimal';
import { useIsDesktop } from '@/lib/use-media-query';
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

/** Сумма дня и её знак. Ни то, ни другое здесь не считается — только оформляется. */
function money(day: CalendarDay): { text: string; tone: string } {
  const formatted = formatMoney(day.net_pnl);
  return {
    text: formatted ?? t.dashboard.unknownValue,
    tone: pnlToneClass(decimalSign(day.net_pnl) ?? 'zero'),
  };
}

function dayLink(day: CalendarDay, cell: CalendarCell): { to: string; label: string } {
  const formatted = formatMoney(day.net_pnl);
  return {
    to: journalDayLink(day.starts_at, day.ends_at),
    label: t.dashboard.calendarDayLabel(cell.dayOfMonth, day.trades, formatted ?? day.net_pnl),
  };
}

function Cell({ cell, today }: { cell: CalendarCell; today: string }) {
  const isToday = cell.iso === today;
  const day = cell.day;
  const sum = day === null ? null : money(day);

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
      {day === null || sum === null ? null : (
        <>
          {/* 11 px, а не 12: на самом узком настольном экране (768 px) ячейка держит
              81 px, и лишний кегль обрезал бы уже пятизначную сумму дня. */}
          <span className={cn('truncate text-[11px] font-medium tabular-nums', sum.tone)}>
            {sum.text}
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
  const link = dayLink(day, cell);
  return (
    <Link to={link.to} aria-label={link.label} className={cn(className, 'hover:bg-accent/50')}>
      {body}
    </Link>
  );
}

function MonthGrid({
  weeks,
  title,
  today,
}: {
  weeks: readonly CalendarWeek[];
  title: string;
  today: string;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] table-fixed border-separate border-spacing-1">
        <caption className="sr-only">{title}</caption>
        <thead>
          <tr>
            {t.dashboard.calendarWeekdays.map((weekday) => (
              <th
                key={weekday}
                scope="col"
                className="pb-1 text-center text-[11px] font-normal text-muted-foreground"
              >
                {weekday}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week, weekIndex) => (
            <tr key={`week-${weekIndex}`}>
              {week.map((cell, dayIndex) =>
                cell === null ? (
                  <td key={`empty-${weekIndex}-${dayIndex}`} />
                ) : (
                  <td key={cell.iso}>
                    <Cell cell={cell} today={today} />
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DayRow({ cell, today }: { cell: TradedCell; today: string }) {
  const isToday = cell.iso === today;
  const link = dayLink(cell.day, cell);
  const sum = money(cell.day);

  return (
    <li>
      <Link
        to={link.to}
        aria-label={link.label}
        className={cn(
          'flex items-center justify-between gap-3 rounded-md border p-2.5 hover:bg-accent/50',
          isToday ? 'border-ring' : 'border-border',
        )}
      >
        <span className="flex min-w-0 flex-col">
          <span className={cn('text-sm', isToday ? 'font-semibold' : 'font-medium')}>
            {t.dashboard.calendarRowDay(
              t.dashboard.calendarWeekdays[cell.weekday] ?? '',
              cell.dayOfMonth,
            )}
            {isToday ? <span className="sr-only"> ({t.dashboard.calendarToday})</span> : null}
          </span>
          <span className="text-xs text-muted-foreground">
            {t.dashboard.calendarTrades(cell.day.trades)}
          </span>
        </span>
        {/* Сумма во всю оставшуюся ширину строки: обрезать её тут нечему. */}
        <span className={cn('shrink-0 text-sm font-medium tabular-nums', sum.tone)}>
          {sum.text}
        </span>
      </Link>
    </li>
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
  const isDesktop = useIsDesktop();
  const weeks = month === undefined ? [] : buildMonthGrid(month.month, month.days);
  const title = month === undefined ? t.dashboard.calendarTitle : monthTitle(month.month);

  return (
    <DashboardBlock title={title} hint={t.dashboard.calendarHint}>
      <BlockStatus query={query} failedMessage={t.dashboard.calendarFailed} />
      {month === undefined ? null : (
        <>
          {month.days.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t.dashboard.calendarEmpty}</p>
          ) : null}
          {isDesktop ? (
            <MonthGrid weeks={weeks} title={title} today={today} />
          ) : (
            <ul className="flex flex-col gap-1.5">
              {tradedCells(weeks).map((cell) => (
                <DayRow key={cell.iso} cell={cell} today={today} />
              ))}
            </ul>
          )}
        </>
      )}
    </DashboardBlock>
  );
}
