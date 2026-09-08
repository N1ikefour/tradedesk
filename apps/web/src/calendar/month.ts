/**
 * Месяц календаря строкой `yyyy-MM`: разбор адреса, переключение месяцев и заголовок.
 *
 * Здесь только арифметика номера месяца — какой месяц идёт до и после этого. Отнесения
 * сделки к дню и границ дня тут нет и быть не может: их считает сервер и присылает
 * готовыми у каждого дня (`docs/metrics.md` §2.2).
 *
 * Пределы повторяют пределы сервера (`analytics/schemas.py`): год 2000–2100, иначе
 * `GET /journal/calendar` отвечает `400`. Продублированы они не ради валидации, а ради
 * её отсутствия на экране — месяц из чужой ссылки подрезается до допустимого, и запрос
 * уходит заведомо принимаемым вместо ошибки вместо календаря.
 */
import { t } from '@/i18n';

const MONTH_PATTERN = /^(\d{4})-(0[1-9]|1[0-2])$/;

/** Месяц живёт в адресе: экран восстанавливается после перезагрузки и уезжает ссылкой. */
export const MONTH_PARAM = 'month';

export const MIN_YEAR = 2000;
export const MAX_YEAR = 2100;

const MONTHS_IN_YEAR = 12;
const MONTH_DIGITS = 2;
/** Длина `yyyy-MM` в строке `yyyy-MM-dd`. */
const MONTH_LENGTH = 7;

export type YearMonth = {
  readonly year: number;
  /** Номер месяца 1–12, как в строке, а не индекс. */
  readonly month: number;
};

export function parseMonth(value: string): YearMonth | null {
  const matched = MONTH_PATTERN.exec(value.trim());
  if (matched === null) {
    return null;
  }
  const year = Number(matched[1]);
  if (year < MIN_YEAR || year > MAX_YEAR) {
    return null;
  }
  return { year, month: Number(matched[2]) };
}

export function formatMonth({ year, month }: YearMonth): string {
  return `${year}-${String(month).padStart(MONTH_DIGITS, '0')}`;
}

/** Месяц торгового дня `yyyy-MM-dd` — им открывается календарь по умолчанию. */
export function monthOfDay(day: string): string {
  return day.slice(0, MONTH_LENGTH);
}

/**
 * Соседний месяц. `null` — за пределами того, что принимает сервер: кнопка в этом месте
 * выключается, а не отправляет запрос, который вернётся `400`.
 */
export function shiftMonth(month: string, delta: number): string | null {
  const parsed = parseMonth(month);
  if (parsed === null) {
    return null;
  }
  const index = parsed.year * MONTHS_IN_YEAR + (parsed.month - 1) + delta;
  const shifted = {
    year: Math.floor(index / MONTHS_IN_YEAR),
    month: (index % MONTHS_IN_YEAR) + 1,
  };
  if (shifted.year < MIN_YEAR || shifted.year > MAX_YEAR) {
    return null;
  }
  return formatMonth(shifted);
}

/**
 * Месяц из адреса. Непонятное значение не показывается ошибкой, а просто не применяется:
 * человек, открывший чужую ссылку с мусором в параметре, должен увидеть свой календарь, а
 * не разбор её синтаксиса (то же правило, что у фильтров журнала).
 */
export function readMonth(raw: string | null, fallback: string): string {
  if (raw === null) {
    return fallback;
  }
  const parsed = parseMonth(raw);
  return parsed === null ? fallback : formatMonth(parsed);
}

/** `Сентябрь 2026`. Неразобранный месяц показывается как есть — выдумывать чужой незачем. */
export function monthTitle(month: string): string {
  const parsed = parseMonth(month);
  if (parsed === null) {
    return month;
  }
  return t.calendar.monthTitle(parsed.month - 1, parsed.year);
}
