/**
 * Календарь — SPEC.md 9.1 `/calendar`, содержимое 9.3.
 *
 * ⚠️ Главный инвариант экрана: **границы торгового дня приходят с сервера**. У каждого дня
 * ответа есть `starts_at`/`ends_at`, и клик по дню открывает журнал ими же плюс
 * `status=closed` (`calendar/day-link.ts`). Второй реализации правила дня здесь нет ни в
 * каком виде: разойдясь, календарь показал бы сделку в понедельник, а журнал за
 * понедельник её не нашёл бы.
 *
 * `trading-day.ts` на этом экране участвует ровно в одном: «какой сейчас торговый день»,
 * чтобы открыть текущий месяц и подсветить сегодняшнюю ячейку (`docs/metrics.md` §2.2).
 * Относить сделку к дню он не должен и не может — сделок этот экран не видит вовсе.
 *
 * Месяц живёт в адресе (`?month=2026-09`): экран переживает перезагрузку и уезжает
 * ссылкой. Счета — из глобального переключателя в шапке (SPEC.md 9.2), поэтому смена
 * выбора меняет ключ запроса и обновляет экран без перезагрузки.
 */
import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router';

import { useAccounts } from '@/accounts/api';
import { useAccountIds } from '@/accounts/selection';
import { messageForError } from '@/api/error-message';
import { calendarParams, useCalendarMonth } from '@/calendar/api';
import { accountsById } from '@/calendar/day-view';
import { buildMonthGrid } from '@/calendar/grid';
import { MONTH_PARAM, monthOfDay, monthTitle, readMonth, shiftMonth } from '@/calendar/month';
import { MonthTotals } from '@/calendar/month-totals';
import { MonthView } from '@/calendar/month-view';
import { totalsOf } from '@/calendar/totals';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { t } from '@/i18n';
import { tradingDayIso } from '@/lib/trading-day';
import { useProfileDayBoundaryHour, useProfileTimeZone } from '@/user/profile';

export function CalendarPage() {
  const [params, setParams] = useSearchParams();
  const timeZone = useProfileTimeZone();
  const dayBoundaryHour = useProfileDayBoundaryHour();
  const selection = useAccountIds();
  const accounts = useAccounts(false);

  // Момент берётся один раз на набор настроек, а не тикающими часами: сегодняшний день —
  // часть ключа месяца по умолчанию, и сдвиг на секунду перезапрашивал бы экран.
  const today = useMemo(
    () => tradingDayIso(new Date(), timeZone, dayBoundaryHour),
    [timeZone, dayBoundaryHour],
  );
  const currentMonth = monthOfDay(today);
  const month = readMonth(params.get(MONTH_PARAM), currentMonth);

  const accountIds = selection.ids;
  const query = useMemo(() => calendarParams(month, accountIds), [month, accountIds]);
  // Выбор, под который не подошёл ни один счёт, спрашивать не о чем: пустой `account_ids`
  // в контракте означает «все счета», и ответ показал бы ровно то, что выбор исключил.
  const asked = selection.ready && !selection.empty;
  const calendar = useCalendarMonth(query, asked);

  // Сетка рисуется по месяцу ответа, пока он есть: тогда дни и заголовок заведомо об
  // одном месяце. Пока ответа нет — по запрошенному, чтобы экран не прыгал.
  const shownMonth = calendar.data?.month ?? month;
  const days = useMemo(() => calendar.data?.days ?? [], [calendar.data]);
  const weeks = useMemo(() => buildMonthGrid(shownMonth, days), [shownMonth, days]);
  const totals = useMemo(() => totalsOf(days), [days]);
  const knownAccounts = useMemo(() => accountsById(accounts.data?.items ?? []), [accounts.data]);

  const title = monthTitle(shownMonth);
  const previous = shiftMonth(month, -1);
  const next = shiftMonth(month, 1);
  const noAccounts = accounts.isSuccess && accounts.data.items.length === 0;

  const goToMonth = (value: string) => {
    const nextParams = new URLSearchParams(params);
    // Текущий месяц — состояние по умолчанию, и в адресе его нет: ссылка на «просто
    // календарь» не должна тащить за собой месяц, в котором её отправили.
    if (value === currentMonth) {
      nextParams.delete(MONTH_PARAM);
    } else {
      nextParams.set(MONTH_PARAM, value);
    }
    setParams(nextParams, { replace: true });
  };

  return (
    <section className="flex w-full flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{t.pages.calendar}</h1>
        <p className="text-sm text-muted-foreground">{t.calendar.hint}</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label={t.calendar.prevMonth}
          disabled={previous === null}
          onClick={() => {
            if (previous !== null) {
              goToMonth(previous);
            }
          }}
        >
          ←
        </Button>
        <span className="min-w-40 text-center text-base font-medium">{title}</span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label={t.calendar.nextMonth}
          disabled={next === null}
          onClick={() => {
            if (next !== null) {
              goToMonth(next);
            }
          }}
        >
          →
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={month === currentMonth}
          onClick={() => goToMonth(currentMonth)}
        >
          {t.calendar.currentMonth}
        </Button>
      </div>

      {selection.empty ? (
        <div className="flex flex-col items-start gap-3 rounded-lg border border-border p-6">
          <p className="text-sm">{t.calendar.emptyRealAccounts}</p>
          <Button type="button" variant="outline" size="sm" asChild>
            <Link to="/accounts">{t.calendar.goToAccounts}</Link>
          </Button>
        </div>
      ) : null}

      {calendar.isPending && asked ? (
        <p className="text-sm text-muted-foreground">{t.common.loading}</p>
      ) : null}

      {calendar.isError ? (
        <div className="flex flex-col items-start gap-3">
          <Alert variant="destructive">
            {t.calendar.failed} {messageForError(calendar.error)}
          </Alert>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={calendar.isFetching}
            onClick={() => {
              void calendar.refetch();
            }}
          >
            {t.common.retry}
          </Button>
        </div>
      ) : null}

      {calendar.isSuccess ? (
        <>
          {days.length === 0 ? (
            <div className="flex flex-col items-start gap-3 rounded-lg border border-border p-6">
              {noAccounts ? (
                <>
                  <p className="text-sm">{t.calendar.emptyAccounts}</p>
                  <Button type="button" variant="outline" size="sm" asChild>
                    <Link to="/accounts">{t.calendar.goToAccounts}</Link>
                  </Button>
                </>
              ) : (
                <>
                  <p className="text-sm">{t.calendar.empty}</p>
                  <p className="text-sm text-muted-foreground">{t.calendar.emptyHint}</p>
                </>
              )}
            </div>
          ) : (
            <MonthTotals totals={totals} />
          )}
          {/* Сетка остаётся на месте и в пустом месяце: она показывает, за какой период
              сказано «сделок нет». Числа в ней при этом не появляются из ниоткуда —
              пустая ячейка это день, которого нет в ответе. */}
          <MonthView
            weeks={weeks}
            title={title}
            today={today}
            variant="full"
            accounts={knownAccounts}
          />
        </>
      ) : null}
    </section>
  );
}
