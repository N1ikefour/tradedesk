/**
 * Сетка месяца для календаря-мини. Сетку рисует фронт, а дни приносит сервер
 * (`docs/metrics.md` §5): в ответе только дни, где была хотя бы одна закрытая позиция,
 * поэтому пустая ячейка — это день, которого в ответе нет, а не потерянные данные.
 *
 * Здесь только календарная арифметика — сколько дней в месяце и с какого дня недели он
 * начинается. Отнесения сделки к дню в этом модуле нет: у каждого дня уже есть готовые
 * `starts_at`/`ends_at`, и ссылка в журнал строится ими.
 */
import { getDay, getDaysInMonth, parseISO } from 'date-fns';

import type { CalendarDay } from '@/dashboard/api';

export type CalendarCell = {
  /** `yyyy-MM-dd` — им же сравнивается «сегодня». */
  readonly iso: string;
  readonly dayOfMonth: number;
  /** День из ответа сервера. `null` — в этом дне закрытых сделок не было. */
  readonly day: CalendarDay | null;
};

/** `null` — пустое место до первого или после последнего числа месяца. */
export type CalendarWeek = readonly (CalendarCell | null)[];

const WEEK_LENGTH = 7;
/** `getDay` считает от воскресенья, а неделя на экране начинается с понедельника. */
const MONDAY_SHIFT = 6;
const DAY_DIGITS = 2;
const MONTH_PATTERN = /^\d{4}-\d{2}$/;

function isoDay(month: string, dayOfMonth: number): string {
  return `${month}-${String(dayOfMonth).padStart(DAY_DIGITS, '0')}`;
}

/**
 * `month` — `yyyy-MM` из ответа календаря. Неразобранный месяц даёт пустую сетку, а не
 * подставленный текущий: нарисованный не тот месяц выглядел бы достоверно.
 */
export function buildMonthGrid(month: string, days: readonly CalendarDay[]): CalendarWeek[] {
  if (!MONTH_PATTERN.test(month)) {
    return [];
  }
  const first = parseISO(`${month}-01`);
  if (Number.isNaN(first.getTime())) {
    return [];
  }
  const byIso = new Map(days.map((day) => [day.day, day]));
  const lead = (getDay(first) + MONDAY_SHIFT) % WEEK_LENGTH;
  const total = getDaysInMonth(first);

  const cells: (CalendarCell | null)[] = Array.from({ length: lead }, () => null);
  for (let dayOfMonth = 1; dayOfMonth <= total; dayOfMonth += 1) {
    const iso = isoDay(month, dayOfMonth);
    cells.push({ iso, dayOfMonth, day: byIso.get(iso) ?? null });
  }
  while (cells.length % WEEK_LENGTH !== 0) {
    cells.push(null);
  }

  const weeks: CalendarWeek[] = [];
  for (let start = 0; start < cells.length; start += WEEK_LENGTH) {
    weeks.push(cells.slice(start, start + WEEK_LENGTH));
  }
  return weeks;
}
