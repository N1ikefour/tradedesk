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
import { useCallback, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router';

import { useAccounts } from '@/accounts/api';
import { useAccountIds } from '@/accounts/selection';
import { messageForError } from '@/api/error-message';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { t } from '@/i18n';
import { usePositions } from '@/journal/api';
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
import { useProfileDayBoundaryHour, useProfileTimeZone } from '@/user/profile';

export function JournalPage() {
  const [params, setParams] = useSearchParams();
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

  const positions = usePositions(queryParams, selection.ready);
  const items = positions.data ?? [];

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
  const loadMore = useCallback(() => {
    // Провалившаяся догрузка не повторяется сама: иначе конец списка превращается в
    // бесконечный цикл запросов, которого человек не видит и не может остановить.
    if (hasNextPage && !isFetchingNextPage && !isFetchNextPageError) {
      void fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage]);

  const noAccounts = accounts.isSuccess && accounts.data.items.length === 0;
  const filtered = !isDefaultFilters(filters);

  return (
    <section className="flex w-full flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{t.pages.journal}</h1>
        <p className="text-sm text-muted-foreground">{t.journal.hint}</p>
      </div>

      <FiltersPanel filters={filters} timeZone={timeZone} onChange={applyFilters} />

      {positions.isPending ? (
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
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      void fetchNextPage();
                    }}
                  >
                    {t.journal.loadMore}
                  </Button>
                </>
              ) : null}
              {!hasNextPage && !isFetchingNextPage ? <span>{t.journal.allLoaded}</span> : null}
            </div>
          }
        />
      ) : null}
    </section>
  );
}
