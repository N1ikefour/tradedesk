import { describe, expect, it } from 'vitest';

import type { CalendarDay } from '@/dashboard/api';
import { buildMonthGrid } from '@/dashboard/calendar-grid';

function day(iso: string): CalendarDay {
  return {
    day: iso,
    starts_at: `${iso}T00:00:00Z`,
    ends_at: `${iso}T23:59:59Z`,
    trades: 3,
    wins: 2,
    losses: 1,
    breakeven: 0,
    net_pnl: '10.00',
    by_account: [],
  };
}

describe('сетка месяца', () => {
  it('сентябрь 2026 начинается со вторника: один пустой день перед первым числом', () => {
    const weeks = buildMonthGrid('2026-09', []);

    expect(weeks).toHaveLength(5);
    expect(weeks[0]?.[0]).toBeNull();
    expect(weeks[0]?.[1]?.dayOfMonth).toBe(1);
    expect(weeks[0]?.[1]?.iso).toBe('2026-09-01');
    // Последнее число месяца — 30-е, дальше только пустые места.
    expect(weeks.flat().filter((cell) => cell !== null)).toHaveLength(30);
  });

  it('месяц, начинающийся с воскресенья, не съезжает на неделю', () => {
    const weeks = buildMonthGrid('2026-02', []);

    expect(weeks[0]?.slice(0, 6).every((cell) => cell === null)).toBe(true);
    expect(weeks[0]?.[6]?.dayOfMonth).toBe(1);
    expect(weeks.flat().filter((cell) => cell !== null)).toHaveLength(28);
  });

  it('день из ответа ложится в свою ячейку, остальные остаются пустыми', () => {
    const weeks = buildMonthGrid('2026-09', [day('2026-09-07')]);
    const cells = weeks.flat().filter((cell) => cell !== null);

    expect(cells.find((cell) => cell.iso === '2026-09-07')?.day?.trades).toBe(3);
    // Пустая ячейка — это день, которого нет в ответе, а не потерянные данные.
    expect(cells.filter((cell) => cell.day !== null)).toHaveLength(1);
  });

  it('неразобранный месяц даёт пустую сетку, а не чужой месяц', () => {
    expect(buildMonthGrid('2026-13', [])).toEqual([]);
    expect(buildMonthGrid('нет', [])).toEqual([]);
  });
});
