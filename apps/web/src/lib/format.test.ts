import { describe, expect, it } from 'vitest';

import {
  formatDateTime,
  formatHourOfDay,
  formatTradingDay,
  formatZonedDateTime,
} from '@/lib/format';
import { browserTimeZone } from '@/lib/time-zones';

const UTC_NOON = '2026-09-02T12:03:00Z';

describe('formatDateTime', () => {
  it('UTC из API переводится в зону пользователя', () => {
    expect(formatDateTime(UTC_NOON, 'Asia/Yekaterinburg')).toBe('02.09.2026 17:03');
    expect(formatDateTime(UTC_NOON, 'Europe/Moscow')).toBe('02.09.2026 15:03');
    expect(formatDateTime(UTC_NOON, 'America/New_York')).toBe('02.09.2026 08:03');
  });

  it('незнакомая движку зона не роняет экран, а показывает время по компьютеру', () => {
    expect(formatDateTime(UTC_NOON, 'Mars/Olympus')).toBe(
      formatDateTime(UTC_NOON, browserTimeZone()),
    );
  });

  it('нечитаемая дата возвращается как есть, а не как «Invalid Date»', () => {
    expect(formatDateTime('не дата', 'Europe/Moscow')).toBe('не дата');
  });
});

describe('formatZonedDateTime', () => {
  it('момент показывается в переданной зоне', () => {
    expect(formatZonedDateTime(new Date('2026-09-05T18:34:00Z'), 'Europe/Moscow')).toBe(
      '05.09.2026 21:34',
    );
  });
});

describe('formatHourOfDay', () => {
  it('час границы дня показывается временем', () => {
    expect(formatHourOfDay(0)).toBe('00:00');
    expect(formatHourOfDay(7)).toBe('07:00');
    expect(formatHourOfDay(23)).toBe('23:00');
  });
});

describe('formatTradingDay', () => {
  const evening = new Date('2026-09-05T18:34:00Z'); // 21:34 в Москве

  it('после границы день календарный', () => {
    expect(formatTradingDay(evening, 'Europe/Moscow', 0)).toBe('05.09.2026');
    expect(formatTradingDay(evening, 'Europe/Moscow', 21)).toBe('05.09.2026');
  });

  it('до границы — предыдущий торговый день', () => {
    expect(formatTradingDay(evening, 'Europe/Moscow', 22)).toBe('04.09.2026');
  });

  it('граница считается по зоне пользователя, а не по UTC', () => {
    // 04:30 UTC — это 07:30 в Москве: граница 7 часов уже пройдена там и ещё нет здесь.
    const morning = new Date('2026-09-06T04:30:00Z');

    expect(formatTradingDay(morning, 'Europe/Moscow', 7)).toBe('06.09.2026');
    expect(formatTradingDay(morning, 'UTC', 7)).toBe('05.09.2026');
  });

  it('переход через начало месяца', () => {
    const firstHours = new Date('2026-09-01T00:30:00Z'); // 03:30 1 сентября в Москве

    expect(formatTradingDay(firstHours, 'Europe/Moscow', 7)).toBe('31.08.2026');
  });
});
