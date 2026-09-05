/**
 * Список таймзон — данные, а не строки интерфейса, поэтому он не в `i18n/ru.ts`.
 *
 * Источник — сам движок: `Intl.supportedValuesOf('timeZone')` возвращает имена IANA из
 * той же базы, которой пользуется `date-fns-tz` при форматировании, и обновляется вместе
 * с браузером. Свой список в репозитории пришлось бы догонять за tzdata (несколько
 * релизов в год), а серверного списка контракт не отдаёт.
 *
 * Набор движка и набор сервера могут не совпадать по псевдонимам (`Europe/Kiev` против
 * `Europe/Kyiv`), поэтому сохранённое значение всегда добавляется в список отдельно —
 * `buildTimeZoneOptions`. Свои имена мы не придумываем: что не из этого списка, того
 * пользователь не выберет, а последнее слово всё равно за валидацией сервера.
 */
import { getTimezoneOffset } from 'date-fns-tz';

/**
 * Резерв для движков без `supportedValuesOf` (Safari до 15.4). Не «весь мир», а зоны
 * бирж и стран, откуда торгуют: длинный ручной список в резерве устареет молча.
 */
const FALLBACK_TIME_ZONES = [
  'UTC',
  'Europe/London',
  'Europe/Lisbon',
  'Europe/Berlin',
  'Europe/Warsaw',
  'Europe/Kaliningrad',
  'Europe/Minsk',
  'Europe/Kiev',
  'Europe/Moscow',
  'Europe/Istanbul',
  'Africa/Cairo',
  'Africa/Johannesburg',
  'Asia/Jerusalem',
  'Asia/Dubai',
  'Asia/Baku',
  'Asia/Tbilisi',
  'Asia/Karachi',
  'Asia/Kolkata',
  'Asia/Tashkent',
  'Asia/Almaty',
  'Asia/Yekaterinburg',
  'Asia/Novosibirsk',
  'Asia/Krasnoyarsk',
  'Asia/Irkutsk',
  'Asia/Bangkok',
  'Asia/Shanghai',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Asia/Vladivostok',
  'Australia/Sydney',
  'Pacific/Auckland',
  'America/Sao_Paulo',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
] as const;

/** Зона без региона (`UTC`) попадает в группу со своим же именем. */
const NO_REGION = 'UTC';

export type TimeZoneOption = {
  /** Имя IANA — оно же значение, которое уходит на сервер. */
  readonly name: string;
  /** Подпись в списке: имя и смещение на сейчас. */
  readonly label: string;
  /** Первый сегмент имени: по нему список делится на `optgroup`. */
  readonly region: string;
};

export type TimeZoneGroup = {
  readonly region: string;
  readonly options: readonly TimeZoneOption[];
};

type SupportedValuesOf = (key: 'timeZone') => string[];

function supportedTimeZones(): readonly string[] {
  // Метода нет в lib ES2022, а на старых движках нет и в рантайме — одна проверка
  // закрывает оба случая и обходится без `any`.
  const supportedValuesOf = (Intl as { supportedValuesOf?: SupportedValuesOf }).supportedValuesOf;
  if (typeof supportedValuesOf !== 'function') {
    return FALLBACK_TIME_ZONES;
  }
  try {
    const values = supportedValuesOf('timeZone');
    return values.length > 0 ? values : FALLBACK_TIME_ZONES;
  } catch {
    return FALLBACK_TIME_ZONES;
  }
}

/** Зона браузера. Она же значение по умолчанию, пока профиль не загружен. */
export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** Знает ли движок такое имя. Незнакомое имя роняет `Intl` исключением, а не значением. */
export function isKnownTimeZone(name: string): boolean {
  if (name === '') {
    return false;
  }
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: name });
    return true;
  } catch {
    return false;
  }
}

/** `UTC+3`, `UTC+5:45`, `UTC-4`. Пустая строка — если движок зону не знает. */
export function offsetLabel(name: string, at: Date): string {
  const offsetMs = getTimezoneOffset(name, at);
  if (!Number.isFinite(offsetMs)) {
    return '';
  }
  const totalMinutes = Math.round(offsetMs / 60_000);
  const sign = totalMinutes < 0 ? '-' : '+';
  const absMinutes = Math.abs(totalMinutes);
  const hours = Math.floor(absMinutes / 60);
  const minutes = absMinutes % 60;
  const tail = minutes === 0 ? '' : `:${String(minutes).padStart(2, '0')}`;
  return `UTC${sign}${hours}${tail}`;
}

function regionOf(name: string): string {
  const slash = name.indexOf('/');
  return slash === -1 ? NO_REGION : name.slice(0, slash);
}

function toOption(name: string, at: Date): TimeZoneOption {
  const offset = offsetLabel(name, at);
  return {
    name,
    label: offset === '' ? name : `${name} (${offset})`,
    region: regionOf(name),
  };
}

/**
 * Список для выпадающего меню. `ensure` — значение из профиля: оно остаётся выбираемым,
 * даже если движок его не знает, иначе экран молча подменил бы человеку сохранённую зону.
 */
export function buildTimeZoneOptions(at: Date, ensure?: string): readonly TimeZoneOption[] {
  const names = new Set(supportedTimeZones());
  if (ensure !== undefined && ensure !== '') {
    names.add(ensure);
  }
  return [...names].sort((a, b) => a.localeCompare(b, 'en')).map((name) => toOption(name, at));
}

/** Пробелы и подчёркивания в поиске равны: «new york» находит `America/New_York`. */
function normalize(value: string): string {
  return value
    .toLowerCase()
    .replace(/[\s_]+/g, ' ')
    .trim();
}

export function filterTimeZoneOptions(
  options: readonly TimeZoneOption[],
  query: string,
): readonly TimeZoneOption[] {
  const needle = normalize(query);
  if (needle === '') {
    return options;
  }
  return options.filter((option) => normalize(option.name).includes(needle));
}

/**
 * Выбранная зона остаётся в списке при любом поиске: `select` без своего значения
 * показал бы чужое и молча подменил бы выбор при следующем сохранении.
 */
export function withSelectedTimeZone(
  visible: readonly TimeZoneOption[],
  all: readonly TimeZoneOption[],
  selected: string,
): readonly TimeZoneOption[] {
  if (visible.some((option) => option.name === selected)) {
    return visible;
  }
  const option = all.find((candidate) => candidate.name === selected);
  return option === undefined ? visible : [option, ...visible];
}

export function groupTimeZoneOptions(options: readonly TimeZoneOption[]): readonly TimeZoneGroup[] {
  const groups: TimeZoneGroup[] = [];
  const index = new Map<string, TimeZoneOption[]>();
  for (const option of options) {
    let bucket = index.get(option.region);
    if (bucket === undefined) {
      bucket = [];
      index.set(option.region, bucket);
      groups.push({ region: option.region, options: bucket });
    }
    bucket.push(option);
  }
  return groups;
}
