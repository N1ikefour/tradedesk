/**
 * Запросы дашборда. Все числа берутся с сервера готовыми: `GET /analytics/summary` и
 * `GET /journal/calendar` (SPEC.md 5.4, 5.5; запрос календаря живёт в `calendar/api.ts` —
 * он общий с экраном `/calendar`). Ни одна величина здесь не собирается
 * сложением загруженных строк — список курсорный, и сумма видимого была бы неотличимым
 * от правды враньём (`docs/metrics.md` §1.1).
 */
import { useQuery } from '@tanstack/react-query';

import { accountIdsParam } from '@/accounts/selection';
import { api, unwrap } from '@/api/client';
import type { components, operations } from '@/api/schema';
import type { DashboardPeriod } from '@/dashboard/period';
import { positionsQueryKey, type PositionsQueryParams } from '@/journal/api';

export type Summary = components['schemas']['SummaryResponse'];

export type SummaryQueryParams = NonNullable<
  operations['read_summary_api_v1_analytics_summary_get']['parameters']['query']
>;

export const SUMMARY_QUERY_KEY = ['analytics', 'summary'] as const;

/**
 * Сколько открытых позиций показывает список. Их немного по природе вещей, а полный
 * перечень открытых — это журнал с фильтром «Открытые», куда и ведёт ссылка.
 */
export const OPEN_POSITIONS_LIMIT = 10;

/**
 * Предел, до которого «сделок без рефлексии» называется точным числом.
 *
 * Общего числа строк список не отдаёт намеренно: `count(*)` по журналу стоит как сама
 * страница (SPEC.md 5.4). Поэтому число берётся не из длины страницы «как получилось»:
 * страница запрашивается вместе с курсором, и **пустой курсор — доказательство**, что
 * страница и есть всё множество. Пришёл курсор — значит строк больше, и на экране будет
 * «больше 20», а не выдуманный итог по первым двадцати.
 */
export const UNREFLECTED_PROBE_LIMIT = 20;

export type CountProbe = {
  readonly count: number;
  /** `true` — счёт точный: сервер сказал, что продолжения нет. */
  readonly exact: boolean;
};

export function summaryParams(
  period: DashboardPeriod,
  accountIds: readonly string[],
): SummaryQueryParams {
  const params: SummaryQueryParams = { from: period.from };
  const ids = accountIdsParam(accountIds);
  if (ids !== undefined) {
    params.account_ids = ids;
  }
  return params;
}

/**
 * Открытые позиции — весь список, без нижней границы периода: позиция, открытая три
 * месяца назад, открыта и сейчас, а период сводки к ней отношения не имеет.
 */
export function openPositionsParams(accountIds: readonly string[]): PositionsQueryParams {
  const params: PositionsQueryParams = {
    status: 'open',
    sort: 'open_time:desc',
    limit: OPEN_POSITIONS_LIMIT,
  };
  const ids = accountIdsParam(accountIds);
  if (ids !== undefined) {
    params.account_ids = ids;
  }
  return params;
}

/** Сделки без рефлексии — тот же период и то же множество, что у сводки: закрытые. */
export function unreflectedParams(
  period: DashboardPeriod,
  accountIds: readonly string[],
): PositionsQueryParams {
  const params: PositionsQueryParams = {
    status: 'closed',
    has_reflection: false,
    from: period.from,
    sort: 'close_time:desc',
    limit: UNREFLECTED_PROBE_LIMIT,
  };
  const ids = accountIdsParam(accountIds);
  if (ids !== undefined) {
    params.account_ids = ids;
  }
  return params;
}

/**
 * Есть ли у пользователя хоть одна заполненная рефлексия — галочка онбординга. Счета в
 * запрос не идут: шаги онбординга описывают состояние человека целиком, а не то, что он
 * выбрал в переключателе, — иначе галочка снималась бы переключением счёта.
 */
export const FIRST_REFLECTION_PARAMS: PositionsQueryParams = {
  has_reflection: true,
  limit: 1,
};

export function useSummary(params: SummaryQueryParams, enabled: boolean) {
  return useQuery({
    queryKey: [...SUMMARY_QUERY_KEY, params],
    queryFn: () => unwrap(api.GET('/api/v1/analytics/summary', { params: { query: params } })),
    enabled,
  });
}

export function useOpenPositions(params: PositionsQueryParams, enabled: boolean) {
  return useQuery({
    queryKey: positionsQueryKey(params),
    queryFn: () => unwrap(api.GET('/api/v1/journal/positions', { params: { query: params } })),
    enabled,
  });
}

/** Число сделок без рефлексии — точное, пока сервер не сказал, что есть продолжение. */
export function useUnreflectedCount(params: PositionsQueryParams, enabled: boolean) {
  return useQuery({
    queryKey: positionsQueryKey(params),
    queryFn: () => unwrap(api.GET('/api/v1/journal/positions', { params: { query: params } })),
    enabled,
    select: (page): CountProbe => ({
      count: page.items.length,
      exact: page.next_cursor === null,
    }),
  });
}

export function useHasAnyReflection(enabled: boolean) {
  return useQuery({
    queryKey: positionsQueryKey(FIRST_REFLECTION_PARAMS),
    queryFn: () =>
      unwrap(api.GET('/api/v1/journal/positions', { params: { query: FIRST_REFLECTION_PARAMS } })),
    enabled,
    select: (page): boolean => page.items.length > 0,
  });
}
