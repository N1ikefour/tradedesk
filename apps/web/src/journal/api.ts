/**
 * Журнал — `GET /journal/positions` (SPEC.md 5.4). Типы берутся из сгенерированной схемы
 * (`make types`), рукописных описаний контракта здесь нет.
 *
 * Пагинация курсорная, и общего числа строк в ответе **нет намеренно**: `count(*)` по
 * журналу стоит столько же, сколько сама страница. Значит «страница 3 из 47» на этом
 * контракте не рисуется, и список догружается страницами по мере прокрутки.
 */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components, operations } from '@/api/schema';

export type PositionListItem = components['schemas']['PositionListItem'];
export type PositionCard = components['schemas']['PositionCard'];
export type Deal = components['schemas']['DealResponse'];
export type JournalEntryDetail = components['schemas']['JournalEntryDetail'];
export type ReflectionDetail = components['schemas']['ReflectionDetail'];
/**
 * Тела обоих `PUT` — из схемы, а не свои. В них **нет необязательных полей** (SPEC.md
 * 5.4): `PUT` заменяет запись целиком, поэтому пропущенное поле означало бы «сотри его».
 * Пока тело собирается как значение этого типа, частичное тело не компилируется.
 */
export type JournalEntryUpdate = components['schemas']['JournalEntryUpdate'];
export type ReflectionUpdate = components['schemas']['ReflectionUpdate'];
export type Tag = components['schemas']['TagResponse'];
export type Vocab = components['schemas']['VocabResponse'];
export type PositionsPage = components['schemas']['PositionsPage'];
export type AccountBrief = components['schemas']['AccountBrief'];

export type PositionsQueryParams = NonNullable<
  operations['list_positions_api_v1_journal_positions_get']['parameters']['query']
>;

export const JOURNAL_QUERY_KEY = ['journal'] as const;

/**
 * Ключ всех страниц списка. Отдельно от `JOURNAL_QUERY_KEY` затем, что карточка и
 * словари живут под тем же корнем: сброс списка после сохранения не должен утаскивать
 * за собой карточку, которая открыта прямо сейчас и уже знает свежий ответ сервера.
 */
export const POSITIONS_QUERY_KEY = [...JOURNAL_QUERY_KEY, 'positions'] as const;
export const TAGS_QUERY_KEY = [...JOURNAL_QUERY_KEY, 'tags'] as const;
export const VOCAB_QUERY_KEY = [...JOURNAL_QUERY_KEY, 'vocab'] as const;

/** Размер страницы. Сервер разрешает до 200, но страница — это ещё и объём JSON. */
export const PAGE_SIZE = 50;

const TAGS_STALE_MS = 5 * 60 * 1000;

/**
 * Предел ожидания записи. Отказ приходит сразу только там, где сеть о себе сообщает;
 * соединение, оставшееся без ответа (уснувший Wi-Fi, прокси в середине), не падает
 * вовсе — и без предела индикатор навсегда застывал бы на «Сохранение…», которое человек
 * читает как «сохранено». Пятнадцать секунд — заведомо больше нормального ответа
 * локального API и заведомо меньше терпения человека.
 */
const SAVE_TIMEOUT_MS = 15_000;

function saveTimeout(): AbortSignal | undefined {
  // `AbortSignal.timeout` есть не во всех средах (jsdom тестов — одна из них).
  return typeof AbortSignal.timeout === 'function'
    ? AbortSignal.timeout(SAVE_TIMEOUT_MS)
    : undefined;
}

export function positionsQueryKey(params: PositionsQueryParams) {
  return [...POSITIONS_QUERY_KEY, params] as const;
}

export function positionQueryKey(positionId: string) {
  return [...JOURNAL_QUERY_KEY, 'position', positionId] as const;
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

/** Карточка позиции — `GET /journal/positions/{id}` (SPEC.md 5.4). */
export function usePosition(positionId: string) {
  return useQuery({
    queryKey: positionQueryKey(positionId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/journal/positions/{position_id}', {
          params: { path: { position_id: positionId } },
        }),
      ),
  });
}

/**
 * Словарь тегов пользователя — подсказки в поле тегов. Список маленький и меняется редко,
 * поэтому за время работы с карточкой не перезапрашивается.
 */
export function useJournalTags() {
  return useQuery({
    queryKey: TAGS_QUERY_KEY,
    queryFn: () => unwrap(api.GET('/api/v1/journal/tags')),
    staleTime: TAGS_STALE_MS,
  });
}

/**
 * Словари рефлексии — SPEC.md 3.5. Значения приходят с сервера, подписи к ним живут в
 * `i18n`: набор ключей закреплён схемой, поэтому неизвестный ключ формой не предлагается.
 *
 * Запрос не повторяется в течение сессии: словарь меняется только вместе с версией API.
 */
export function useVocab() {
  return useQuery({
    queryKey: VOCAB_QUERY_KEY,
    queryFn: () => unwrap(api.GET('/api/v1/journal/vocab')),
    staleTime: Infinity,
  });
}

/**
 * Запись идёт даже при выключенной сети — и это осознанно. Библиотека по умолчанию
 * **ставит мутацию на паузу**, пока браузер считает себя офлайн, и отправляет её при
 * возвращении связи. Для карточки это худший из вариантов: индикатор навсегда застывает
 * на «Сохранение…», а человек читает это как «сохранено» и закрывает вкладку. С
 * `networkMode: 'always'` запрос уходит, немедленно падает и превращается в видимую
 * ошибку с кнопкой «Повторить» — а набранное остаётся в форме (SPEC.md 12, DoD S2-07).
 * Проверено в браузере на выключенной сети.
 *
 * С `X-42` то же решение принято для всего клиента (`app-providers.tsx`), и здесь оно
 * остаётся явным: цена ошибки на этих двух мутациях выше, чем где-либо ещё, и держать её
 * рядом с кодом дешевле, чем восстанавливать по умолчанию.
 */
const SAVE_NETWORK_MODE = 'always' as const;

/**
 * Ответ сервера кладётся в карточку как есть: написание тегов он берёт из словаря
 * (`trend` при заведённом `Trend` сохранится как `Trend`), и правда о записи — это он,
 * а не то, что набрано в поле.
 */
export function useSaveEntry(positionId: string) {
  const client = useQueryClient();
  return useMutation({
    networkMode: SAVE_NETWORK_MODE,
    mutationFn: (body: JournalEntryUpdate) =>
      unwrap(
        api.PUT('/api/v1/journal/positions/{position_id}/entry', {
          params: { path: { position_id: positionId } },
          body,
          signal: saveTimeout(),
        }),
      ),
    onSuccess: (entry) => {
      client.setQueryData<PositionCard>(positionQueryKey(positionId), (card) =>
        card === undefined ? card : { ...card, journal_entry: entry },
      );
    },
  });
}

/** То же для рефлексии. `filled_at` считает сервер — клиент его не выдумывает. */
export function useSaveReflection(positionId: string) {
  const client = useQueryClient();
  return useMutation({
    networkMode: SAVE_NETWORK_MODE,
    mutationFn: (body: ReflectionUpdate) =>
      unwrap(
        api.PUT('/api/v1/journal/positions/{position_id}/reflection', {
          params: { path: { position_id: positionId } },
          body,
          signal: saveTimeout(),
        }),
      ),
    onSuccess: (reflection) => {
      client.setQueryData<PositionCard>(positionQueryKey(positionId), (card) =>
        card === undefined ? card : { ...card, reflection },
      );
    },
  });
}
