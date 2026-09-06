import { describe, expect, it } from 'vitest';

import {
  formatDateTime,
  formatHourOfDay,
  formatRelativePast,
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

describe('formatRelativePast', () => {
  const now = new Date('2026-09-02T12:00:00Z');
  const ago = (seconds: number) => new Date(now.getTime() - seconds * 1000).toISOString();

  it('единицу выбирает по возрасту, а склонение — по числу', () => {
    expect(formatRelativePast(ago(5), now)).toBe('только что');
    expect(formatRelativePast(ago(59), now)).toBe('только что');
    expect(formatRelativePast(ago(60), now)).toBe('1 минуту назад');
    expect(formatRelativePast(ago(120), now)).toBe('2 минуты назад');
    expect(formatRelativePast(ago(300), now)).toBe('5 минут назад');
    expect(formatRelativePast(ago(3600), now)).toBe('1 час назад');
    expect(formatRelativePast(ago(3 * 3600), now)).toBe('3 часа назад');
    expect(formatRelativePast(ago(86_400), now)).toBe('1 день назад');
    expect(formatRelativePast(ago(5 * 86_400), now)).toBe('5 дней назад');
  });

  // Часы браузера и сервера расходятся на секунды; отрицательный возраст — не данные,
  // а этот рассинхрон, и «через -3 секунды» было бы хуже, чем «только что».
  it('момент из будущего читается как «только что», а не как отрицательный возраст', () => {
    expect(formatRelativePast(new Date(now.getTime() + 30_000).toISOString(), now)).toBe(
      'только что',
    );
  });

  it('нечитаемая дата возвращается как есть', () => {
    expect(formatRelativePast('не дата', now)).toBe('не дата');
  });
});
