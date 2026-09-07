import { describe, expect, it } from 'vitest';

import { periodStart, tradingDate, tradingDayIso, tradingDayStart } from '@/lib/trading-day';

const MOSCOW = 'Europe/Moscow';
const NEW_YORK = 'America/New_York';

/** Календарная дата как носитель, а не как момент, — так её и строит модуль. */
function day(year: number, month: number, date: number): Date {
  return new Date(year, month - 1, date);
}

describe('tradingDate', () => {
  it('час до границы принадлежит вчерашнему торговому дню', () => {
    // 06:00 в Москве при границе 07:00 — это ещё вчера.
    const at = new Date('2026-09-06T03:00:00Z');

    expect(tradingDate(at, MOSCOW, 7).getDate()).toBe(5);
  });

  it('час после границы — сегодняшний день', () => {
    const at = new Date('2026-09-06T05:00:00Z');

    expect(tradingDate(at, MOSCOW, 7).getDate()).toBe(6);
  });

  it('считает по зоне пользователя, а не по UTC', () => {
    // 23:30 UTC — это уже 6 сентября в Москве, при границе 0 день сменился.
    const at = new Date('2026-09-05T23:30:00Z');

    expect(tradingDate(at, MOSCOW, 0).getDate()).toBe(6);
    expect(tradingDate(at, 'UTC', 0).getDate()).toBe(5);
  });
});

describe('tradingDayStart', () => {
  it('переводит границу дня в момент UTC по смещению зоны', () => {
    expect(tradingDayStart(day(2026, 9, 6), MOSCOW, 7).toISOString()).toBe(
      '2026-09-06T04:00:00.000Z',
    );
  });

  it('смещение берётся на саму дату, а не на сегодня: переход на зимнее время', () => {
    // 1 ноября 2025 Нью-Йорк ещё на летнем времени (UTC−4), 5 ноября — уже на зимнем.
    expect(tradingDayStart(day(2025, 11, 1), NEW_YORK, 0).toISOString()).toBe(
      '2025-11-01T04:00:00.000Z',
    );
    expect(tradingDayStart(day(2025, 11, 5), NEW_YORK, 0).toISOString()).toBe(
      '2025-11-05T05:00:00.000Z',
    );
  });

  it('час границы за пределами суток не уводит дату', () => {
    expect(tradingDayStart(day(2026, 9, 6), 'UTC', 42).toISOString()).toBe(
      '2026-09-06T23:00:00.000Z',
    );
  });

  it('незнакомая движку зона не роняет расчёт', () => {
    expect(() => tradingDayStart(day(2026, 9, 6), 'Мордор/Барад-Дур', 0)).not.toThrow();
  });
});

describe('periodStart', () => {
  const now = new Date('2026-09-06T05:00:00Z');

  it('«всё» не даёт нижней границы', () => {
    expect(periodStart('all', now, MOSCOW, 7)).toBeNull();
  });

  it('«сегодня» — начало текущего торгового дня', () => {
    expect(periodStart('today', now, MOSCOW, 7)?.toISOString()).toBe('2026-09-06T04:00:00.000Z');
  });

  it('«неделя» — семь торговых дней, считая сегодняшний', () => {
    expect(periodStart('week', now, MOSCOW, 7)?.toISOString()).toBe('2026-08-31T04:00:00.000Z');
  });

  it('«месяц» — тридцать дней назад по календарю', () => {
    expect(periodStart('month', now, MOSCOW, 7)?.toISOString()).toBe('2026-08-08T04:00:00.000Z');
  });

  it('до границы дня период отсчитывается от вчерашнего дня', () => {
    const beforeBoundary = new Date('2026-09-06T03:00:00Z');

    expect(periodStart('today', beforeBoundary, MOSCOW, 7)?.toISOString()).toBe(
      '2026-09-05T04:00:00.000Z',
    );
  });
});

/**
 * Примеры `docs/metrics.md` §2.4 — те же, по которым проверяется серверное правило дня.
 * Долг на этот тест записан там же (§8): без него совпадение двух реализаций держалось
 * на глазах ревьюера. Отнесение сделки к дню считает сервер, но «какой сейчас торговый
 * день» фронт называет сам, и разойтись с сервером он не должен.
 */
describe('tradingDayIso: общие примеры с сервером', () => {
  const YEKATERINBURG = 'Asia/Yekaterinburg';
  const BERLIN = 'Europe/Berlin';

  it.each([
    [YEKATERINBURG, 0, '2026-09-01T18:30:00Z', '2026-09-01'],
    [YEKATERINBURG, 0, '2026-09-01T19:30:00Z', '2026-09-02'],
    [YEKATERINBURG, 6, '2026-09-02T00:30:00Z', '2026-09-01'],
    [YEKATERINBURG, 6, '2026-09-02T01:30:00Z', '2026-09-02'],
    // Ночь перевода часов: сутки длятся 25 часов, а день определён интервалом.
    [BERLIN, 0, '2026-10-25T22:30:00Z', '2026-10-25'],
    [BERLIN, 0, '2026-10-25T23:30:00Z', '2026-10-26'],
  ])('%s, граница %i, %s → %s', (zone, boundary, moment, expected) => {
    expect(tradingDayIso(new Date(moment), zone, boundary)).toBe(expected);
  });
});
