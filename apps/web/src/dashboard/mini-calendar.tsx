/**
 * Календарь-мини текущего месяца — SPEC.md 9.3.
 *
 * Своего показа месяца у дашборда нет: сетку, список узкого экрана и ссылки в журнал
 * рисует общий `calendar/month-view.tsx`, тот же, что и на экране `/calendar`. Разница
 * между экранами — только в плотности (`variant`) и в том, что мини не показывает итоги
 * недель и разбивку по счетам. Иначе два экрана, читающие один ответ сервера, со временем
 * назвали бы один и тот же день разными числами.
 */
import type { CalendarMonth } from '@/calendar/api';
import { buildMonthGrid } from '@/calendar/grid';
import { monthTitle } from '@/calendar/month';
import { MonthView } from '@/calendar/month-view';
import { BlockStatus, DashboardBlock, type BlockQueryState } from '@/dashboard/block';
import { t } from '@/i18n';

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
  const title = month === undefined ? t.dashboard.calendarTitle : monthTitle(month.month);

  return (
    <DashboardBlock title={title} hint={t.dashboard.calendarHint}>
      <BlockStatus query={query} failedMessage={t.calendar.failed} />
      {month === undefined ? null : (
        <>
          {month.days.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t.calendar.empty}</p>
          ) : null}
          <MonthView weeks={weeks} title={title} today={today} variant="mini" />
        </>
      )}
    </DashboardBlock>
  );
}
