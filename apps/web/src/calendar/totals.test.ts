import { describe, expect, it } from 'vitest';

import type { CalendarDay } from '@/calendar/api';
import { buildMonthGrid } from '@/calendar/grid';
import { totalsOf, weekTotals } from '@/calendar/totals';

function day(iso: string, netPnl: string, trades = 3): CalendarDay {
  return {
    day: iso,
    starts_at: `${iso}T00:00:00Z`,
    ends_at: `${iso}T23:00:00Z`,
    trades,
    wins: 2,
    losses: 1,
    breakeven: 0,
    net_pnl: netPnl,
    by_account: [],
  };
}

describe('итоги календаря', () => {
  it('итог месяца — сумма дней ответа, а не части списка', () => {
    // Месяц приходит одним ответом целиком, поэтому сумма его дней это сумма всего
    // множества (docs/metrics.md §1.1 запрещает как раз обратное).
    const totals = totalsOf([
      day('2026-09-01', '10.50'),
      day('2026-09-02', '-2.25'),
      day('2026-09-03', '0.00'),
    ]);

    expect(totals.netPnl).toBe('8.25');
    expect(totals.trades).toBe(9);
    expect(totals.wins).toBe(6);
    expect(totals.losses).toBe(3);
    expect(totals.days).toBe(3);
  });

  it('деньги складываются точно, а не через double', () => {
    const totals = totalsOf([day('2026-09-01', '0.10'), day('2026-09-02', '0.20')]);

    expect(totals.netPnl).toBe('0.30');
  });

  it('нечитаемая сумма дня даёт прочерк вместо итога, а не итог по остальным', () => {
    const totals = totalsOf([day('2026-09-01', '10.00'), day('2026-09-02', 'нет')]);

    expect(totals.netPnl).toBeNull();
    // Счётчики при этом остаются: они целые числа контракта и от денег не зависят.
    expect(totals.trades).toBe(6);
  });

  it('итог недели берёт только дни из ответа', () => {
    const weeks = buildMonthGrid('2026-09', [
      day('2026-09-01', '10.00'),
      day('2026-09-05', '5.00'),
    ]);
    // Сентябрь 2026 начинается со вторника: первая неделя — 1–6 сентября.
    const first = weekTotals(weeks[0] ?? []);

    expect(first.netPnl).toBe('15.00');
    expect(first.days).toBe(2);
  });

  it('неделя без сделок итога не получает: ноль дней, а не ноль долларов', () => {
    const weeks = buildMonthGrid('2026-09', [day('2026-09-01', '10.00')]);
    const second = weekTotals(weeks[1] ?? []);

    expect(second.days).toBe(0);
    expect(second.trades).toBe(0);
  });
});
