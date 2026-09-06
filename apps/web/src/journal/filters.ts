/**
 * Фильтры журнала живут в адресе (SPEC.md 9.3): состояние списка восстанавливается после
 * перезагрузки и уезжает ссылкой другому человеку.
 *
 * Отсюда главное свойство модуля: **параметр в адресе — чужой ввод.** Его печатает рука,
 * приносит старая ссылка, дописывает почтовик. Ни одно значение не уходит на сервер
 * непроверенным: у `GET /journal/positions` стоит `extra="forbid"`, свои пределы на длину
 * символа, поиска и числа тегов, и любое несоответствие — это `400` вместо журнала.
 * Непонятное значение поэтому не показывается ошибкой, а просто не применяется: человек,
 * открывший чужую ссылку, должен увидеть свои сделки, а не разбор её синтаксиса.
 */
import { accountIdsParam } from '@/accounts/selection';
import type { PositionsQueryParams } from '@/journal/api';
import { PAGE_SIZE } from '@/journal/api';
import { isPeriodPreset, periodStart, type PeriodPreset } from '@/lib/trading-day';

export const SORT_FIELDS = [
  'close_time',
  'open_time',
  'net_pnl',
  'symbol_norm',
  'duration_seconds',
] as const;

export type SortField = (typeof SORT_FIELDS)[number];
export type SortDirection = (typeof SORT_DIRECTIONS)[number];

export const STATUS_VALUES = ['open', 'closed'] as const;
export const DIRECTION_VALUES = ['long', 'short'] as const;
export const RESULT_VALUES = ['win', 'loss', 'be'] as const;
export const REFLECTION_VALUES = ['filled', 'none'] as const;
export const SORT_DIRECTIONS = ['asc', 'desc'] as const;

export type PositionStatus = (typeof STATUS_VALUES)[number];
export type PositionDirection = (typeof DIRECTION_VALUES)[number];
export type PositionResult = (typeof RESULT_VALUES)[number];
export type ReflectionFilter = (typeof REFLECTION_VALUES)[number];

/** «Свой период» приходит только ссылкой — например, из календаря (`S2-09`). */
export type PeriodValue = PeriodPreset | 'custom';

export type JournalFilters = {
  readonly period: PeriodValue;
  readonly from: string | null;
  readonly to: string | null;
  readonly status: PositionStatus | null;
  readonly symbol: string;
  readonly direction: PositionDirection | null;
  readonly result: PositionResult | null;
  readonly tags: readonly string[];
  readonly reflection: ReflectionFilter | null;
  readonly q: string;
  readonly sortField: SortField;
  readonly sortDirection: SortDirection;
};

export const PARAM = {
  period: 'period',
  from: 'from',
  to: 'to',
  status: 'status',
  symbol: 'symbol',
  direction: 'direction',
  result: 'result',
  tags: 'tags',
  reflection: 'reflection',
  q: 'q',
  sort: 'sort',
} as const;

/**
 * Периода по умолчанию нет намеренно. Любой другой — это спрятанные сделки на первом же
 * экране: человек, у которого месяц не было сделок, увидел бы пустой журнал и решил, что
 * синк не работает.
 */
export const DEFAULT_FILTERS: JournalFilters = {
  period: 'all',
  from: null,
  to: null,
  status: null,
  symbol: '',
  direction: null,
  result: null,
  tags: [],
  reflection: null,
  q: '',
  sortField: 'close_time',
  sortDirection: 'desc',
};

// Пределы сервера (`journal/schemas.py`). Продублированы здесь не ради валидации, а ради
// её отсутствия на экране: значение из адреса подрезается до допустимого, и запрос уходит
// заведомо принимаемым вместо `400`.
const MAX_SYMBOL_LENGTH = 32;
const MAX_SEARCH_LENGTH = 100;
const MAX_TAGS = 20;
const MAX_TAG_LENGTH = 64;

const FILTER_SEPARATOR = ',';
const SORT_SEPARATOR = ':';

/**
 * Значение из списка допустимых или `null`. Одна функция и на разбор адреса, и на разбор
 * `<select>`: у обоих источник — строка, которой могло не быть в перечислении.
 */
export function oneOf<T extends string>(value: string | null, allowed: readonly T[]): T | null {
  if (value === null) {
    return null;
  }
  return allowed.find((candidate) => candidate === value) ?? null;
}

function isValidInstant(value: string): boolean {
  return !Number.isNaN(new Date(value).getTime());
}

function readSort(raw: string | null): Pick<JournalFilters, 'sortField' | 'sortDirection'> {
  const [field, direction] = (raw ?? '').split(SORT_SEPARATOR);
  const sortField = oneOf(field ?? null, SORT_FIELDS);
  const sortDirection = oneOf(direction ?? null, SORT_DIRECTIONS);
  if (sortField === null || sortDirection === null) {
    return { sortField: DEFAULT_FILTERS.sortField, sortDirection: DEFAULT_FILTERS.sortDirection };
  }
  return { sortField, sortDirection };
}

function readTags(raw: string | null): readonly string[] {
  if (raw === null) {
    return [];
  }
  const seen = new Set<string>();
  for (const part of raw.split(FILTER_SEPARATOR)) {
    const tag = part.trim();
    if (tag !== '' && tag.length <= MAX_TAG_LENGTH) {
      seen.add(tag);
    }
    if (seen.size === MAX_TAGS) {
      break;
    }
  }
  return [...seen];
}

function readPeriod(params: URLSearchParams): Pick<JournalFilters, 'period' | 'from' | 'to'> {
  const from = params.get(PARAM.from);
  const to = params.get(PARAM.to);
  const validFrom = from !== null && isValidInstant(from) ? from : null;
  const validTo = to !== null && isValidInstant(to) ? to : null;
  // Пустой период (`from >= to`) сервер отвергает как ошибку, и он прав: человек читает
  // пустой список как «сделок нет», а не как «границы перепутаны». Здесь такая пара
  // просто не применяется — иначе ссылка с опечаткой давала бы вместо журнала `400`.
  const ordered =
    validFrom !== null && validTo !== null && new Date(validFrom) >= new Date(validTo);
  if (ordered) {
    return { period: DEFAULT_FILTERS.period, from: null, to: null };
  }
  if (validFrom !== null || validTo !== null) {
    return { period: 'custom', from: validFrom, to: validTo };
  }
  const period = params.get(PARAM.period);
  return {
    period: period !== null && isPeriodPreset(period) ? period : DEFAULT_FILTERS.period,
    from: null,
    to: null,
  };
}

export function readFilters(params: URLSearchParams): JournalFilters {
  return {
    ...readPeriod(params),
    status: oneOf(params.get(PARAM.status), STATUS_VALUES),
    symbol: (params.get(PARAM.symbol) ?? '').trim().slice(0, MAX_SYMBOL_LENGTH),
    direction: oneOf(params.get(PARAM.direction), DIRECTION_VALUES),
    result: oneOf(params.get(PARAM.result), RESULT_VALUES),
    tags: readTags(params.get(PARAM.tags)),
    reflection: oneOf(params.get(PARAM.reflection), REFLECTION_VALUES),
    q: (params.get(PARAM.q) ?? '').trim().slice(0, MAX_SEARCH_LENGTH),
    ...readSort(params.get(PARAM.sort)),
  };
}

/**
 * Фильтры → адрес. Значения по умолчанию не пишутся: чистый экран должен давать чистый
 * адрес, иначе ссылка на «просто журнал» тащит за собой десяток параметров.
 */
export function writeFilters(filters: JournalFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.period === 'custom') {
    if (filters.from !== null) {
      params.set(PARAM.from, filters.from);
    }
    if (filters.to !== null) {
      params.set(PARAM.to, filters.to);
    }
  } else if (filters.period !== DEFAULT_FILTERS.period) {
    params.set(PARAM.period, filters.period);
  }
  if (filters.status !== null) {
    params.set(PARAM.status, filters.status);
  }
  if (filters.symbol !== '') {
    params.set(PARAM.symbol, filters.symbol);
  }
  if (filters.direction !== null) {
    params.set(PARAM.direction, filters.direction);
  }
  if (filters.result !== null) {
    params.set(PARAM.result, filters.result);
  }
  if (filters.tags.length > 0) {
    params.set(PARAM.tags, filters.tags.join(FILTER_SEPARATOR));
  }
  if (filters.reflection !== null) {
    params.set(PARAM.reflection, filters.reflection);
  }
  if (filters.q !== '') {
    params.set(PARAM.q, filters.q);
  }
  if (
    filters.sortField !== DEFAULT_FILTERS.sortField ||
    filters.sortDirection !== DEFAULT_FILTERS.sortDirection
  ) {
    params.set(PARAM.sort, `${filters.sortField}${SORT_SEPARATOR}${filters.sortDirection}`);
  }
  return params;
}

export function isDefaultFilters(filters: JournalFilters): boolean {
  return writeFilters(filters).toString() === '';
}

export type QueryContext = {
  readonly accountIds: readonly string[];
  readonly now: Date;
  readonly timeZone: string;
  readonly dayBoundaryHour: number;
};

/**
 * Фильтры → параметры запроса. Пресет разворачивается в момент запроса и по зоне
 * пользователя: «сегодня» это его торговый день, а не сутки UTC (SPEC.md 3).
 *
 * Ключи собираются перечислением, а не переносом объекта фильтров: у эндпоинта
 * `extra="forbid"`, и любое лишнее поле, случайно попавшее в запрос, стоило бы `400`.
 */
export function toQueryParams(
  filters: JournalFilters,
  context: QueryContext,
): PositionsQueryParams {
  const params: PositionsQueryParams = {
    sort: `${filters.sortField}${SORT_SEPARATOR}${filters.sortDirection}`,
    limit: PAGE_SIZE,
  };
  const accountIds = accountIdsParam(context.accountIds);
  if (accountIds !== undefined) {
    params.account_ids = accountIds;
  }
  if (filters.period === 'custom') {
    if (filters.from !== null) {
      params.from = new Date(filters.from).toISOString();
    }
    if (filters.to !== null) {
      params.to = new Date(filters.to).toISOString();
    }
  } else {
    const from = periodStart(
      filters.period,
      context.now,
      context.timeZone,
      context.dayBoundaryHour,
    );
    if (from !== null) {
      params.from = from.toISOString();
    }
  }
  if (filters.status !== null) {
    params.status = filters.status;
  }
  if (filters.symbol !== '') {
    params.symbol = filters.symbol;
  }
  if (filters.direction !== null) {
    params.direction = filters.direction;
  }
  if (filters.result !== null) {
    params.result = filters.result;
  }
  if (filters.tags.length > 0) {
    params.tags = filters.tags.join(FILTER_SEPARATOR);
  }
  if (filters.reflection !== null) {
    params.has_reflection = filters.reflection === 'filled';
  }
  if (filters.q !== '') {
    params.q = filters.q;
  }
  return params;
}
