/**
 * Журнал — SPEC.md 9.1 `/journal`, содержимое 9.3.
 *
 * Сводки за фильтр здесь нет, и это решение, а не пропуск. `SPEC.md` 9.3 берёт её из
 * `GET /analytics/summary`, а эндпоинта ещё нет — он приходит в `S2-05`. Считать те же
 * числа на фронте нельзя: пагинация курсорная, загружено не всё, и сумма по видимым
 * строкам была бы враньём, неотличимым от правды. Заглушка с прочерками на месте
 * будущей шапки — тоже вранье, только про поломку: пустая рамка вверху экрана читается
 * как «не загрузилось». Поэтому блока нет вовсе; он встанет между заголовком и панелью
 * фильтров, когда появится, чем брать числа.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, Outlet, useMatch, useSearchParams } from 'react-router';

import { useAccounts } from '@/accounts/api';
import { useAccountIds } from '@/accounts/selection';
import { messageForError } from '@/api/error-message';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { t } from '@/i18n';
import { usePositions, type PositionListItem } from '@/journal/api';
import { FiltersPanel } from '@/journal/filters-panel';
import {
  DEFAULT_FILTERS,
  isDefaultFilters,
  readFilters,
  toQueryParams,
  writeFilters,
  type JournalFilters,
  type SortField,
} from '@/journal/filters';
import { PositionsList } from '@/journal/positions-list';
import { useIsDesktop } from '@/lib/use-media-query';
import { useProfileDayBoundaryHour, useProfileTimeZone } from '@/user/profile';

/**
 * Сколько страниц подряд догрузка терпит, не получив ни одной новой строки. Признак
 * конца списка — `next_cursor` сервера, то есть чужое обещание: сервер, отдающий пустую
 * страницу с новым курсором, превращал бы прокрутку в непрерывный поток запросов,
 * которого человек не видит и не может остановить. Сегодняшний сервер так не отвечает —
 * но список останавливает себя сам, а не полагается на это.
 */
const MAX_IDLE_PAGES = 3;

/**
 * Что карточка позиции видит от своего списка. Соседей для «← предыдущая / следующая →»
 * взять больше неоткуда: список курсорный, эндпоинта «соседи» в контракте нет, а карточка
 * живёт вложенным маршрутом ровно затем, чтобы читать загруженные строки отсюда.
 */
export type JournalListContext = {
  readonly items: readonly PositionListItem[];
};

export function JournalPage() {
  const [params, setParams] = useSearchParams();
  // Карточка позиции — вложенный маршрут (SPEC.md 9.1): на большом экране она модал
  // поверх таблицы, на телефоне — страница, и тогда список под ней не рисуется.
  const cardOpen = useMatch('/journal/:id') !== null;
  const isDesktop = useIsDesktop();
  const showList = isDesktop || !cardOpen;
  const filters = useMemo(() => readFilters(params), [params]);
  const timeZone = useProfileTimeZone();
  const dayBoundaryHour = useProfileDayBoundaryHour();
  const selection = useAccountIds();
  const accounts = useAccounts(false);

  const accountIds = selection.ids;
  const queryParams = useMemo(
    // Момент берётся здесь, а не тикающими часами: пресет «сегодня» обязан быть
    // стабильным ключом запроса, иначе список перезапрашивался бы каждую секунду.
    () => toQueryParams(filters, { accountIds, now: new Date(), timeZone, dayBoundaryHour }),
    [filters, accountIds, timeZone, dayBoundaryHour],
  );

  // Выбор, под который не подходит ни один счёт, спрашивать не о чем: пустой
  // `account_ids` означает «все счета», и запрос вернул бы ровно то, что выбор исключил.
  // Скрытый список не запрашивается: по прямой ссылке на карточку с телефона журнал
  // человеку не показан, и грузить его страницами незачем. Уже загруженные строки при
  // этом остаются доступными — их отдаёт кэш, а не запрос.
  const positions = usePositions(queryParams, selection.ready && !selection.empty && showList);
  const items = positions.data ?? [];
  const outletContext: JournalListContext = { items };

  const applyFilters = (next: JournalFilters) => {
    setParams(writeFilters(next), { replace: true });
  };

  const sortBy = (field: SortField) => {
    applyFilters(
      filters.sortField === field
        ? { ...filters, sortDirection: filters.sortDirection === 'asc' ? 'desc' : 'asc' }
        : { ...filters, sortField: field, sortDirection: 'desc' },
    );
  };

  const { hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = positions;
  const loaded = items.length;
  const idle = useRef({ loaded: -1, pages: 0 });
  const [autoPaused, setAutoPaused] = useState(false);

  useEffect(() => {
    // Смена фильтра или счёта — это другой список, и счётчик холостых страниц к нему
    // отношения не имеет.
    idle.current = { loaded: -1, pages: 0 };
    setAutoPaused(false);
  }, [queryParams]);

  const loadMore = useCallback(() => {
    // Провалившаяся догрузка не повторяется сама: иначе конец списка превращается в
    // бесконечный цикл запросов, которого человек не видит и не может остановить.
    if (!hasNextPage || isFetchingNextPage || isFetchNextPageError) {
      return;
    }
    if (idle.current.loaded !== loaded) {
      idle.current = { loaded, pages: 0 };
    } else if (idle.current.pages >= MAX_IDLE_PAGES) {
      setAutoPaused(true);
      return;
    } else {
      idle.current.pages += 1;
    }
    void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage, loaded]);

  /** Ручная догрузка — решение человека, поэтому счётчик холостых страниц обнуляется. */
  const loadMoreManually = useCallback(() => {
    idle.current = { loaded: -1, pages: 0 };
    setAutoPaused(false);
    void fetchNextPage();
  }, [fetchNextPage]);

  const noAccounts = accounts.isSuccess && accounts.data.items.length === 0;
  const filtered = !isDefaultFilters(filters);

  if (!showList) {
    return <Outlet context={outletContext} />;
  }

  return (
    <section className="flex w-full flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{t.pages.journal}</h1>
        <p className="text-sm text-muted-foreground">{t.journal.hint}</p>
      </div>

      <FiltersPanel filters={filters} timeZone={timeZone} onChange={applyFilters} />

      {selection.empty ? (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-border p-6">
          <p className="text-sm">{t.journal.emptyRealAccounts}</p>
          <Button type="button" variant="outline" size="sm" asChild>
            <Link to="/accounts">{t.journal.goToAccounts}</Link>
          </Button>
        </div>
      ) : null}

      {positions.isPending && !selection.empty ? (
        <p className="text-sm text-muted-foreground">{t.common.loading}</p>
      ) : null}

      {positions.isError ? (
        <div className="flex flex-col items-start gap-3">
          <Alert variant="destructive">
            {t.journal.loadFailed} {messageForError(positions.error)}
          </Alert>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={positions.isFetching}
            onClick={() => {
              void positions.refetch();
            }}
          >
            {t.common.retry}
          </Button>
        </div>
      ) : null}

      {positions.isSuccess && items.length === 0 ? (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-border p-6">
          {noAccounts ? (
            <>
              <p className="text-sm">{t.journal.emptyAccounts}</p>
              <Button type="button" variant="outline" size="sm" asChild>
                <Link to="/accounts">{t.journal.goToAccounts}</Link>
              </Button>
            </>
          ) : filtered ? (
            <>
              <p className="text-sm">{t.journal.emptyFiltered}</p>
              <p className="text-sm text-muted-foreground">{t.journal.emptyFilteredHint}</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => applyFilters(DEFAULT_FILTERS)}
              >
                {t.journal.resetFilters}
              </Button>
            </>
          ) : (
            <>
              <p className="text-sm">{t.journal.empty}</p>
              <p className="text-sm text-muted-foreground">{t.journal.emptyHint}</p>
              <Button type="button" variant="outline" size="sm" asChild>
                <Link to="/accounts">{t.journal.goToAccounts}</Link>
              </Button>
            </>
          )}
        </div>
      ) : null}

      {items.length > 0 ? (
        <PositionsList
          items={items}
          timeZone={timeZone}
          sort={filters}
          onSortChange={sortBy}
          onReachEnd={loadMore}
          footer={
            <div className="flex flex-wrap items-center gap-3 border-t border-border px-3 py-2 text-xs text-muted-foreground">
              <span>{t.journal.loadedCount(items.length)}</span>
              {isFetchingNextPage ? <span>{t.journal.loadingMore}</span> : null}
              {isFetchNextPageError ? (
                <>
                  <span className="text-destructive">{t.journal.loadMoreFailed}</span>
                  <Button type="button" variant="outline" size="sm" onClick={loadMoreManually}>
                    {t.journal.loadMore}
                  </Button>
                </>
              ) : null}
              {autoPaused && hasNextPage && !isFetchingNextPage && !isFetchNextPageError ? (
                <>
                  <span>{t.journal.loadMorePaused}</span>
                  <Button type="button" variant="outline" size="sm" onClick={loadMoreManually}>
                    {t.journal.loadMore}
                  </Button>
                </>
              ) : null}
              {!hasNextPage && !isFetchingNextPage ? <span>{t.journal.allLoaded}</span> : null}
            </div>
          }
        />
      ) : null}

      <Outlet context={outletContext} />
    </section>
  );
}
