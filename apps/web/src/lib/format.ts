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

import { t } from '@/i18n';
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

const SECONDS_IN_MINUTE = 60;
const SECONDS_IN_HOUR = 60 * SECONDS_IN_MINUTE;
const SECONDS_IN_DAY = 24 * SECONDS_IN_HOUR;

/**
 * «2 мин назад» для статусов — SPEC.md 9.4. Слова берутся из словаря, здесь только выбор
 * единицы: склонения и сами формулировки живут в `i18n`, а не расползаются по экранам.
 *
 * Момент из будущего — не ошибка данных, а рассинхрон часов браузера и сервера на
 * несколько секунд. Он читается как «только что»: отрицательный возраст показывать нечем.
 */
export function formatRelativePast(iso: string, now: Date): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) {
    return iso;
  }
  const seconds = Math.floor((now.getTime() - at.getTime()) / 1000);
  if (seconds < SECONDS_IN_MINUTE) {
    return t.time.justNow;
  }
  if (seconds < SECONDS_IN_HOUR) {
    return t.time.minutesAgo(Math.floor(seconds / SECONDS_IN_MINUTE));
  }
  if (seconds < SECONDS_IN_DAY) {
    return t.time.hoursAgo(Math.floor(seconds / SECONDS_IN_HOUR));
  }
  return t.time.daysAgo(Math.floor(seconds / SECONDS_IN_DAY));
}
