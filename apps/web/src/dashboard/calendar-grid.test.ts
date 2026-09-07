import { describe, expect, it } from 'vitest';

import type { CalendarDay } from '@/dashboard/api';
import { buildMonthGrid, tradedCells } from '@/dashboard/calendar-grid';

function nextDay(iso: string): string {
  const at = new Date(`${iso}T00:00:00Z`);
  at.setUTCDate(at.getUTCDate() + 1);
  return at.toISOString().slice(0, 'yyyy-MM-dd'.length);
}

/**
 * День таким, каким его отдаёт сервер: `ends_at` — **начало следующего дня**, потому что
 * торговый день это полуинтервал `[начало(D), начало(D+1))` (`docs/metrics.md` §2.1).
 * Написать сюда `23:59:59` значило бы закрепить в фикстуре форму, которой в ответе нет.
 */
function day(iso: string): CalendarDay {
  return {
    day: iso,
    starts_at: `${iso}T00:00:00Z`,
    ends_at: `${nextDay(iso)}T00:00:00Z`,
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

  it('день недели у ячейки тот же, что колонка сетки: им подписан список на телефоне', () => {
    const weeks = buildMonthGrid('2026-09', []);
    const cells = weeks.flat().filter((cell) => cell !== null);

    // 1 сентября 2026 — вторник: вторая колонка, индекс 1.
    expect(cells.find((cell) => cell.dayOfMonth === 1)?.weekday).toBe(1);
    expect(cells.find((cell) => cell.dayOfMonth === 6)?.weekday).toBe(6);
    expect(cells.find((cell) => cell.dayOfMonth === 7)?.weekday).toBe(0);
    // Столбец сетки и день недели ячейки — одно и то же число, иначе список и сетка
    // назвали бы один день разными днями недели.
    for (const week of weeks) {
      week.forEach((cell, index) => {
        if (cell !== null) {
          expect(cell.weekday).toBe(index);
        }
      });
    }
  });
});

describe('список торговых дней', () => {
  it('берёт только дни из ответа и сохраняет их порядок', () => {
    const weeks = buildMonthGrid('2026-09', [day('2026-09-07'), day('2026-09-02')]);

    expect(tradedCells(weeks).map((cell) => cell.iso)).toEqual(['2026-09-02', '2026-09-07']);
    // Границы дня в список попадают из ответа как есть — второго правила дня тут нет.
    expect(tradedCells(weeks)[0]?.day.ends_at).toBe('2026-09-03T00:00:00Z');
  });

  it('месяц без сделок даёт пустой список, а не строки с прочерками', () => {
    expect(tradedCells(buildMonthGrid('2026-09', []))).toEqual([]);
  });
});
