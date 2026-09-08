/**
 * Итоги недели и месяца — SPEC.md 9.3 («Итоги по неделям справа, по месяцу сверху»).
 *
 * ⚠️ Это **единственные** числа экрана, которые считает клиент, и законны они по одной
 * причине: месяц приходит одним ответом целиком, значит сумма дней — это сумма всего
 * множества, а не видимой части (`docs/metrics.md` §1.1 запрещает как раз второе). Сами
 * дни, их границы и их суммы считает сервер.
 *
 * Деньги складываются `sumDecimals`, то есть на `BigInt`: `Number` на `numeric(18,2)`
 * дал бы итог недели, не совпадающий с суммой её же дней на копейку. Счётчики сделок —
 * целые числа контракта (SPEC.md 5.5, «счётчики отдаются числами»), их складывает `+`.
 */
import type { CalendarDay } from '@/calendar/api';
import type { CalendarWeek } from '@/calendar/grid';
import { sumDecimals } from '@/lib/decimal';

export type CalendarTotals = {
  /** Сумма `net_pnl` дней. `null` — хоть одно слагаемое не разобралось. */
  readonly netPnl: string | null;
  readonly trades: number;
  readonly wins: number;
  readonly losses: number;
  readonly breakeven: number;
  /** Сколько дней с закрытыми сделками попало в итог. Ноль — итога нет вовсе. */
  readonly days: number;
};

export function totalsOf(days: readonly CalendarDay[]): CalendarTotals {
  const totals = {
    trades: 0,
    wins: 0,
    losses: 0,
    breakeven: 0,
    days: days.length,
  };
  for (const day of days) {
    totals.trades += day.trades;
    totals.wins += day.wins;
    totals.losses += day.losses;
    totals.breakeven += day.breakeven;
  }
  return { ...totals, netPnl: sumDecimals(days.map((day) => day.net_pnl)) };
}

/** Дни недели, о которых сервер что-то прислал. Пустая неделя итога не получает. */
export function weekTotals(week: CalendarWeek): CalendarTotals {
  const days: CalendarDay[] = [];
  for (const cell of week) {
    if (cell !== null && cell.day !== null) {
      days.push(cell.day);
    }
  }
  return totalsOf(days);
}
