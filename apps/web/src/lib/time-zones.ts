/**
 * Подписи, поиск и группировка таймзон. Сам список сюда передают — источник его
 * серверный, `GET /users/timezones` (`@/user/time-zones`).
 *
 * Почему не движок. `Intl.supportedValuesOf('timeZone')` отдаёт набор ICU, а принимает
 * имена сервер из своей tzdata, и по псевдонимам наборы расходятся: Chrome знает
 * `Asia/Calcutta` и не знает `Asia/Kolkata`, сервер — ровно наоборот. Для Индии,
 * Украины, Вьетнама, Непала и ещё нескольких стран единственный пункт меню оказывался
 * несохраняемым (`400 validation_error`). Список от сервера и приём на сервере — один
 * набор, расходиться нечему.
 *
 * Резервного списка в репозитории нет намеренно: любой наш список — это снова догадка
 * о том, что примет сервер, то есть та же поломка, только реже. Не пришёл список —
 * зона не меняется, и экран настроек об этом говорит.
 */
import { getTimezoneOffset } from 'date-fns-tz';

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

/**
 * Зона, которую движок точно знает. Зона профиля может быть ему незнакома: наборы имён
 * IANA у браузера и у сервера расходятся по псевдонимам, и падать на этом нельзя —
 * показываем по зоне компьютера, а экран настроек про расхождение предупреждает отдельно.
 */
export function safeTimeZone(timeZone: string): string {
  return isKnownTimeZone(timeZone) ? timeZone : browserTimeZone();
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
 * Список для выпадающего меню из имён, которые прислал сервер. Своих имён функция не
 * добавляет: чего нет в `names`, того сервер и не примет.
 *
 * Исключение одно — `ensure`, сохранённое значение профиля. Оно остаётся выбираемым,
 * даже если его нет ни в ответе сервера, ни у движка: иначе экран молча подменил бы
 * человеку зону при первом же сохранении.
 */
export function buildTimeZoneOptions(
  names: Iterable<string>,
  at: Date,
  ensure?: string,
): readonly TimeZoneOption[] {
  const unique = new Set(names);
  if (ensure !== undefined && ensure !== '') {
    unique.add(ensure);
  }
  return [...unique].sort((a, b) => a.localeCompare(b, 'en')).map((name) => toOption(name, at));
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
