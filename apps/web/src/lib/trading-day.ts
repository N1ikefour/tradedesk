/**
 * Торговый день и периоды фильтра журнала (SPEC.md 9.3 — «период с пресетами»).
 *
 * День у пользователя начинается в `day_boundary_hour` его таймзоны, а не в полночь UTC
 * (SPEC.md 3): ночная сделка европейца принадлежит вчерашнему торговому дню, и «сегодня»
 * обязано считаться так же, иначе фильтр покажет не тот день, чем занят человек.
 *
 * Арифметика идёт по календарной дате, а не вычитанием суток из момента: сутки в зоне
 * пользователя не всегда длятся 24 часа, и «неделя назад» через `−7 × 24 ч` в дни
 * перевода часов промахивается мимо границы дня на час.
 */
import { addDays, format as formatDate, parseISO } from 'date-fns';
import { formatInTimeZone, fromZonedTime } from 'date-fns-tz';

import { safeTimeZone } from '@/lib/time-zones';

export const PERIOD_PRESETS = ['today', 'week', 'month', 'all'] as const;

export type PeriodPreset = (typeof PERIOD_PRESETS)[number];

const ISO_DAY_PATTERN = 'yyyy-MM-dd';
const HOUR_PATTERN = 'H';

const WEEK_DAYS = 7;
const MONTH_DAYS = 30;

const MIN_BOUNDARY_HOUR = 0;
const MAX_BOUNDARY_HOUR = 23;

export function isPeriodPreset(value: string): value is PeriodPreset {
  return (PERIOD_PRESETS as readonly string[]).includes(value);
}

/**
 * Час границы приходит из профиля и проверен сервером (0–23), но экран не должен зависеть
 * от того, что в кэше лежит проверенное значение: `fromZonedTime` со «стеной» `24:00`
 * молча уедет на сутки.
 */
function safeBoundaryHour(hour: number): number {
  if (!Number.isFinite(hour)) {
    return MIN_BOUNDARY_HOUR;
  }
  return Math.min(MAX_BOUNDARY_HOUR, Math.max(MIN_BOUNDARY_HOUR, Math.trunc(hour)));
}

/**
 * Календарная дата торгового дня, которому принадлежит момент `at`. Возвращается как
 * полночь по часам машины — это носитель даты для арифметики, а не момент времени.
 */
export function tradingDate(at: Date, timeZone: string, boundaryHour: number): Date {
  const zone = safeTimeZone(timeZone);
  const boundary = safeBoundaryHour(boundaryHour);
  const day = parseISO(formatInTimeZone(at, zone, ISO_DAY_PATTERN));
  const hour = Number(formatInTimeZone(at, zone, HOUR_PATTERN));
  return hour < boundary ? addDays(day, -1) : day;
}

/**
 * Дата торгового дня строкой `yyyy-MM-dd` — ключ, а не показ: ею сравнивается «сегодня»
 * с днями календаря и из неё берётся месяц запроса. Отнесение **сделки** к дню этим не
 * делается никогда — это работа сервера (`docs/metrics.md` §2.2).
 */
export function tradingDayIso(at: Date, timeZone: string, boundaryHour: number): string {
  return formatDate(tradingDate(at, timeZone, boundaryHour), ISO_DAY_PATTERN);
}

/** Момент, с которого начинается торговый день `date` в зоне пользователя. */
export function tradingDayStart(date: Date, timeZone: string, boundaryHour: number): Date {
  const zone = safeTimeZone(timeZone);
  const hour = String(safeBoundaryHour(boundaryHour)).padStart(2, '0');
  return fromZonedTime(`${formatDate(date, ISO_DAY_PATTERN)}T${hour}:00:00`, zone);
}

/**
 * Начало периода пресета. `null` у «Всё» — это отсутствие нижней границы, а не её
 * бесконечное значение: параметр `from` в таком запросе не отправляется вовсе.
 *
 * Верхней границы у пресетов нет намеренно. Сделка, закрытая минуту назад, обязана
 * попасть в «сегодня», а `to` пришлось бы двигать вместе с часами — и каждое движение
 * перезапрашивало бы список.
 */
export function periodStart(
  preset: Exclude<PeriodPreset, 'all'>,
  now: Date,
  timeZone: string,
  boundaryHour: number,
): Date;
export function periodStart(
  preset: PeriodPreset,
  now: Date,
  timeZone: string,
  boundaryHour: number,
): Date | null;
export function periodStart(
  preset: PeriodPreset,
  now: Date,
  timeZone: string,
  boundaryHour: number,
): Date | null {
  if (preset === 'all') {
    return null;
  }
  const today = tradingDate(now, timeZone, boundaryHour);
  const days = preset === 'today' ? 1 : preset === 'week' ? WEEK_DAYS : MONTH_DAYS;
  return tradingDayStart(addDays(today, -(days - 1)), timeZone, boundaryHour);
}
