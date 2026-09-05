/**
 * Форматирование — SPEC.md 9.4. Одно место на всё приложение: `toFixed` и локальные
 * `Intl.*` по компонентам расходятся между экранами.
 *
 * Время приходит из API в UTC (ISO с `Z`), а показывается в таймзоне пользователя из
 * профиля (`/users/me`). Смещение считает `date-fns-tz` — своих вычислений здесь нет.
 *
 * Деньги и цены появятся вместе с экранами, которые их показывают.
 */
import { format, parseISO, subDays } from 'date-fns';
import { formatInTimeZone } from 'date-fns-tz';

import { browserTimeZone, isKnownTimeZone } from '@/lib/time-zones';

const DATE_TIME_PATTERN = 'dd.MM.yyyy HH:mm';
const DAY_PATTERN = 'dd.MM.yyyy';
const ISO_DAY_PATTERN = 'yyyy-MM-dd';
const HOUR_PATTERN = 'H';

/**
 * Зона профиля может быть незнакома движку: наборы имён IANA у браузера и у сервера
 * расходятся по псевдонимам. Падать на этом нельзя — показываем по зоне компьютера,
 * а экран настроек про расхождение предупреждает отдельно.
 */
function safeTimeZone(timeZone: string): string {
  return isKnownTimeZone(timeZone) ? timeZone : browserTimeZone();
}

/** `02.09.2026 17:03` в переданной таймзоне. */
export function formatZonedDateTime(at: Date, timeZone: string): string {
  return formatInTimeZone(at, safeTimeZone(timeZone), DATE_TIME_PATTERN);
}

/** То же для значения из API: `2026-09-02T12:03:00Z` → `02.09.2026 17:03`. */
export function formatDateTime(iso: string, timeZone: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) {
    return iso;
  }
  return formatZonedDateTime(at, timeZone);
}

/** `7` → `07:00`. Час начала торгового дня показывается как время, а не как число. */
export function formatHourOfDay(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`;
}

/**
 * Дата торгового дня для момента `at` — SPEC.md 3: день начинается в `day_boundary_hour`
 * по таймзоне пользователя, а не в полночь UTC. Час до границы принадлежит вчерашнему
 * торговому дню.
 */
export function formatTradingDay(at: Date, timeZone: string, boundaryHour: number): string {
  const zone = safeTimeZone(timeZone);
  const day = formatInTimeZone(at, zone, ISO_DAY_PATTERN);
  const hour = Number(formatInTimeZone(at, zone, HOUR_PATTERN));
  // Арифметика по календарной дате, а не по часам: сутки в зоне пользователя не всегда
  // длятся 24 часа, а нужен именно предыдущий день календаря.
  const start = parseISO(day);
  return format(hour < boundaryHour ? subDays(start, 1) : start, DAY_PATTERN);
}
