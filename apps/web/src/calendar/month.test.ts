import { describe, expect, it } from 'vitest';

import { monthOfDay, monthTitle, parseMonth, readMonth, shiftMonth } from '@/calendar/month';
import { t } from '@/i18n';

describe('месяц календаря', () => {
  it('разбирает только то, что примет сервер', () => {
    expect(parseMonth('2026-09')).toEqual({ year: 2026, month: 9 });
    // Пределы сервера (`analytics/schemas.py`): год 2000–2100, месяц 01–12.
    expect(parseMonth('2026-13')).toBeNull();
    expect(parseMonth('2026-00')).toBeNull();
    expect(parseMonth('1999-12')).toBeNull();
    expect(parseMonth('2101-01')).toBeNull();
    expect(parseMonth('2026-9')).toBeNull();
    expect(parseMonth('сентябрь')).toBeNull();
  });

  it('месяц берётся из торгового дня, а не из часов машины', () => {
    expect(monthOfDay('2026-09-07')).toBe('2026-09');
  });

  it('соседний месяц переходит через год', () => {
    expect(shiftMonth('2026-09', 1)).toBe('2026-10');
    expect(shiftMonth('2026-12', 1)).toBe('2027-01');
    expect(shiftMonth('2026-01', -1)).toBe('2025-12');
    expect(shiftMonth('2026-09', -9)).toBe('2025-12');
  });

  it('за пределами того, что принимает сервер, соседа нет: кнопка выключается', () => {
    // Иначе экран отправил бы запрос, который заведомо вернётся 400.
    expect(shiftMonth('2000-01', -1)).toBeNull();
    expect(shiftMonth('2100-12', 1)).toBeNull();
    expect(shiftMonth('мусор', 1)).toBeNull();
  });

  it('мусор в адресе не показывается ошибкой, а просто не применяется', () => {
    // Человек, открывший чужую ссылку, должен увидеть свой календарь, а не разбор её
    // синтаксиса, — то же правило, что у фильтров журнала.
    expect(readMonth('2026-02', '2026-09')).toBe('2026-02');
    expect(readMonth(null, '2026-09')).toBe('2026-09');
    expect(readMonth('2026-13', '2026-09')).toBe('2026-09');
    expect(readMonth('0001-01', '2026-09')).toBe('2026-09');
    expect(readMonth('%00', '2026-09')).toBe('2026-09');
  });

  it('заголовок называет месяц словом, неразобранный показывает как есть', () => {
    expect(monthTitle('2026-09')).toBe(t.calendar.monthTitle(8, 2026));
    expect(monthTitle('2026-09')).toContain('2026');
    expect(monthTitle('нет')).toBe('нет');
  });
});
