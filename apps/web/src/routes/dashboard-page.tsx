/**
 * Дашборд — SPEC.md 9.1 `/`, содержимое 9.3. Первый экран после входа.
 *
 * Все числа приходят с сервера готовыми: сводку и календарь считает `analytics` (`S2-05`),
 * границы торгового дня — он же. Экран не складывает загруженные строки нигде: список
 * курсорный, видимое ≠ всё, и сумма части выглядела бы как сумма целого.
 *
 * Пока позиций нет ни у одного счёта, метрик на экране нет вовсе — вместо них шаги
 * онбординга. Четыре пустые рамки с прочерками читались бы как поломка, а сегодня это не
 * редкий случай: `positions` наполняет ингест (`S1-04`), которого ещё нет.
 */
import type { FetchStatus } from '@tanstack/react-query';
import { useMemo } from 'react';
import { Link } from 'react-router';

import { useAccounts } from '@/accounts/api';
import { useAccountIds } from '@/accounts/selection';
import { messageForError } from '@/api/error-message';
import { QueryProgress } from '@/components/query-progress';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { calendarParams, useCalendarMonth } from '@/calendar/api';
import {
  openPositionsParams,
  summaryParams,
  unreflectedParams,
  useHasAnyReflection,
  useOpenPositions,
  useSummary,
  useUnreflectedCount,
  type CountProbe,
} from '@/dashboard/api';
import { AttentionBlock } from '@/dashboard/attention-block';
import type { BlockQueryState } from '@/dashboard/block';
import { MiniCalendar } from '@/dashboard/mini-calendar';
import { buildOnboarding, isOnboardingComplete } from '@/dashboard/onboarding';
import { OnboardingBlock } from '@/dashboard/onboarding-block';
import { OpenPositions } from '@/dashboard/open-positions';
import { dashboardPeriod } from '@/dashboard/period';
import { SummaryBlock } from '@/dashboard/summary-block';
import { t } from '@/i18n';
import { useProfileDayBoundaryHour, useProfileTimeZone } from '@/user/profile';

type QueryLike = {
  readonly isPending: boolean;
  readonly isError: boolean;
  readonly error: Error | null;
  readonly isFetching: boolean;
  readonly fetchStatus: FetchStatus;
  readonly refetch: () => Promise<unknown>;
};

/**
 * Состояние запроса для блока. Выключенный запрос у TanStack Query остаётся `pending` —
 * без явного «его не спрашивали» блок показывал бы «Загрузка…», которая никогда не
 * кончится.
 */
function blockState(query: QueryLike, asked: boolean): BlockQueryState {
  if (!asked) {
    return {
      isPending: false,
      isError: false,
      error: null,
      isFetching: false,
      fetchStatus: 'idle',
      refetch: () => {},
    };
  }
  return {
    isPending: query.isPending,
    isError: query.isError,
    error: query.error,
    isFetching: query.isFetching,
    fetchStatus: query.fetchStatus,
    refetch: () => {
      void query.refetch();
    },
  };
}

/** Без единой позиции сделок без рефлексии тоже нет — это доказуемо, а не предположение. */
const NOTHING_UNREFLECTED: CountProbe = { count: 0, exact: true };

export function DashboardPage() {
  const timeZone = useProfileTimeZone();
  const dayBoundaryHour = useProfileDayBoundaryHour();
  const selection = useAccountIds();
  const accounts = useAccounts(false);

  // Момент берётся один раз на набор настроек, а не тикающими часами: период — часть
  // ключа запроса, и сдвиг на секунду перезапрашивал бы весь экран.
  const period = useMemo(
    () => dashboardPeriod(new Date(), timeZone, dayBoundaryHour),
    [timeZone, dayBoundaryHour],
  );

  const accountItems = useMemo(() => accounts.data?.items ?? [], [accounts.data]);
  // Онбординг описывает состояние человека целиком, а не выбранные счета: галочка,
  // снимаемая переключателем, означала бы, что пройденный шаг «отменился».
  const hasAnyPositions = accountItems.some((account) => account.positions_count > 0);

  const accountIds = selection.ids;
  // Выбор, под который не подошёл ни один счёт, спрашивать не о чем: пустой `account_ids`
  // в контракте означает «все счета», и ответ показал бы ровно то, что выбор исключил.
  // Список счетов, не приехавший вовсе, — не повод не показать метрики: тогда работает
  // запасной вариант «все счета», ровно как в журнале.
  const showMetrics = !selection.empty && (hasAnyPositions || accounts.isError);
  const asked = selection.ready && showMetrics;

  // Параметры запоминаются: они же ключи запросов, и новый объект на каждый рендер
  // заставлял бы TanStack Query пересобирать ключ на каждую перерисовку экрана.
  const summaryQuery = useMemo(() => summaryParams(period, accountIds), [period, accountIds]);
  const calendarQuery = useMemo(
    () => calendarParams(period.month, accountIds),
    [period.month, accountIds],
  );
  const openQuery = useMemo(() => openPositionsParams(accountIds), [accountIds]);
  const unreflectedQuery = useMemo(
    () => unreflectedParams(period, accountIds),
    [period, accountIds],
  );

  const summary = useSummary(summaryQuery, asked);
  const calendar = useCalendarMonth(calendarQuery, asked);
  const open = useOpenPositions(openQuery, asked);
  const unreflected = useUnreflectedCount(unreflectedQuery, asked);
  // Рефлексии не может быть там, где нет ни одной позиции, — и спрашивать об этом незачем.
  const reflection = useHasAnyReflection(hasAnyPositions);

  const steps = buildOnboarding({
    accounts: accountItems,
    hasReflection: reflection.data ?? false,
  });
  // Онбординг показывается только по достоверному списку счетов: на неприехавшем списке
  // все галочки были бы сняты, и человек с двумя счетами прочитал бы «начните со счёта».
  const onboarding =
    accounts.isSuccess && !isOnboardingComplete(steps) ? <OnboardingBlock steps={steps} /> : null;
  const attention = accounts.isPending ? null : (
    <AttentionBlock
      accounts={accountItems}
      unreflected={asked ? unreflected.data : NOTHING_UNREFLECTED}
      unreflectedQuery={blockState(unreflected, asked)}
    />
  );

  return (
    <section className="flex w-full flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{t.pages.dashboard}</h1>
        <p className="text-sm text-muted-foreground">{t.dashboard.hint}</p>
      </div>

      {accounts.isError ? (
        <Alert variant="destructive">
          {t.dashboard.loadFailed} {messageForError(accounts.error)}
        </Alert>
      ) : null}

      {accounts.isPending ? <QueryProgress fetchStatus={accounts.fetchStatus} /> : null}

      {selection.empty ? (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-border p-6">
          <p className="text-sm">{t.dashboard.emptyRealAccounts}</p>
          <Button type="button" variant="outline" size="sm" asChild>
            <Link to="/accounts">{t.dashboard.goToAccounts}</Link>
          </Button>
        </div>
      ) : null}

      {/* Пока метрик нет, шаги — главное на экране, а не сноска под ним. */}
      {showMetrics ? null : onboarding}

      {showMetrics ? (
        <>
          <SummaryBlock
            query={blockState(summary, asked)}
            summary={summary.data}
            periodFrom={period.from}
            timeZone={timeZone}
          />
          {/* Календарь во всю ширину: в половине экрана ячейка обрезает сумму дня, а
              обрезанные деньги хуже отсутствующих — их читают как другое число. */}
          <MiniCalendar
            query={blockState(calendar, asked)}
            month={calendar.data}
            today={period.today}
          />
          <div className="grid items-start gap-6 lg:grid-cols-2">
            <OpenPositions query={blockState(open, asked)} page={open.data} timeZone={timeZone} />
            {attention}
          </div>
        </>
      ) : (
        attention
      )}

      {showMetrics ? onboarding : null}
    </section>
  );
}
