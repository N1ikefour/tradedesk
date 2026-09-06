/**
 * Форматирование — SPEC.md 9.4. Одно место на всё приложение: `toFixed` и локальные
 * `Intl.*` по компонентам расходятся между экранами.
 *
 * Время приходит из API в UTC (ISO с `Z`), а показывается в таймзоне пользователя из
 * профиля (`/users/me`). Смещение считает `date-fns-tz` — своих вычислений здесь нет.
 *
 * Деньги, цены и объёмы приходят строками и печатаются в `@/lib/decimal`: там они
 * никогда не становятся `number`, и разделять эти два модуля стоит именно поэтому.
 */
import { format } from 'date-fns';
import { formatInTimeZone } from 'date-fns-tz';

import { t } from '@/i18n';
import { safeTimeZone } from '@/lib/time-zones';
import { tradingDate } from '@/lib/trading-day';

const DATE_TIME_PATTERN = 'dd.MM.yyyy HH:mm';
const DAY_PATTERN = 'dd.MM.yyyy';

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
 * торговому дню. Саму границу считает `@/lib/trading-day` — тот же расчёт стоит под
 * пресетами периода в журнале, и разъехаться этим двум местам нельзя.
 */
export function formatTradingDay(at: Date, timeZone: string, boundaryHour: number): string {
  return format(tradingDate(at, timeZone, boundaryHour), DAY_PATTERN);
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

/**
 * Длительность позиции — колонка журнала (SPEC.md 9.3). Две единицы, не больше: строка
 * стоит в узкой ячейке рядом с ценами, и «1 д 2 ч 3 мин 4 с» там читается хуже, чем
 * «1 д 2 ч», а третья единица ничего не решает при взгляде на список.
 */
export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return t.journal.unknownValue;
  }
  const total = Math.floor(seconds);
  if (total < SECONDS_IN_MINUTE) {
    return t.units.seconds(total);
  }
  if (total < SECONDS_IN_HOUR) {
    const minutes = Math.floor(total / SECONDS_IN_MINUTE);
    const rest = total % SECONDS_IN_MINUTE;
    return rest === 0
      ? t.units.minutes(minutes)
      : `${t.units.minutes(minutes)} ${t.units.seconds(rest)}`;
  }
  if (total < SECONDS_IN_DAY) {
    const hours = Math.floor(total / SECONDS_IN_HOUR);
    const minutes = Math.floor((total % SECONDS_IN_HOUR) / SECONDS_IN_MINUTE);
    return minutes === 0
      ? t.units.hours(hours)
      : `${t.units.hours(hours)} ${t.units.minutes(minutes)}`;
  }
  const days = Math.floor(total / SECONDS_IN_DAY);
  const hours = Math.floor((total % SECONDS_IN_DAY) / SECONDS_IN_HOUR);
  return hours === 0 ? t.units.days(days) : `${t.units.days(days)} ${t.units.hours(hours)}`;
}
