/**
 * Журнал — `GET /journal/positions` (SPEC.md 5.4). Типы берутся из сгенерированной схемы
 * (`make types`), рукописных описаний контракта здесь нет.
 *
 * Пагинация курсорная, и общего числа строк в ответе **нет намеренно**: `count(*)` по
 * журналу стоит столько же, сколько сама страница. Значит «страница 3 из 47» на этом
 * контракте не рисуется, и список догружается страницами по мере прокрутки.
 */
import { useInfiniteQuery } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components, operations } from '@/api/schema';

export type PositionListItem = components['schemas']['PositionListItem'];
export type PositionsPage = components['schemas']['PositionsPage'];
export type AccountBrief = components['schemas']['AccountBrief'];

export type PositionsQueryParams = NonNullable<
  operations['list_positions_api_v1_journal_positions_get']['parameters']['query']
>;

export const JOURNAL_QUERY_KEY = ['journal'] as const;

/** Размер страницы. Сервер разрешает до 200, но страница — это ещё и объём JSON. */
export const PAGE_SIZE = 50;

export function positionsQueryKey(params: PositionsQueryParams) {
  return [...JOURNAL_QUERY_KEY, 'positions', params] as const;
}

export function usePositions(params: PositionsQueryParams, enabled: boolean) {
  return useInfiniteQuery({
    queryKey: positionsQueryKey(params),
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET('/api/v1/journal/positions', {
          params: { query: pageParam === null ? params : { ...params, cursor: pageParam } },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage: PositionsPage) => lastPage.next_cursor,
    enabled,
    // Страницы склеиваются один раз на изменение данных, а не на каждый рендер таблицы:
    // виртуализация перерисовывает её на каждый пиксель прокрутки.
    select: (data) => data.pages.flatMap((page) => page.items),
  });
}
