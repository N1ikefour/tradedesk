/**
 * Период дашборда — SPEC.md 9.3, «Summary за 30 дней».
 *
 * Это **тот же** пресет, что «Месяц» в фильтрах журнала, и берётся он тем же расчётом
 * (`periodStart`), а не своими тридцатью днями. Причина в ссылках: с дашборда человек
 * уходит в журнал за «этот же период», и если бы период считали два места, сумма колонки
 * в журнале не совпала бы со сводкой, из которой человек по ссылке пришёл.
 *
 * Отнесение сделки к дню здесь не считается ничем: `tradingDayIso` даёт только «какой
 * сейчас торговый день» — месяц для запроса календаря и подсветку сегодняшней ячейки
 * (`docs/metrics.md` §2.2).
 */
import { PARAM } from '@/journal/filters';
import { periodStart, tradingDayIso } from '@/lib/trading-day';

const DASHBOARD_PRESET = 'month' as const;

/** Длина `yyyy-MM` в строке `yyyy-MM-dd`. */
const MONTH_LENGTH = 7;

export type DashboardPeriod = {
  /** Нижняя граница периода в UTC (ISO с `Z`) — то, что уходит в `from`. */
  readonly from: string;
  /** Месяц календаря `yyyy-MM` в зоне пользователя. */
  readonly month: string;
  /** Сегодняшний торговый день `yyyy-MM-dd` — им подсвечивается ячейка. */
  readonly today: string;
};

export function dashboardPeriod(
  now: Date,
  timeZone: string,
  boundaryHour: number,
): DashboardPeriod {
  const today = tradingDayIso(now, timeZone, boundaryHour);
  return {
    from: periodStart(DASHBOARD_PRESET, now, timeZone, boundaryHour).toISOString(),
    month: today.slice(0, MONTH_LENGTH),
    today,
  };
}

/**
 * Ссылки в журнал за тот же период. Пресетом, а не границами: журнал развернёт «Месяц»
 * тем же расчётом, и человек увидит на панели фильтров знакомое слово вместо двух дат.
 */
function journalPeriodLink(extra: Readonly<Record<string, string>>): string {
  const params = new URLSearchParams({ [PARAM.period]: DASHBOARD_PRESET, ...extra });
  return `/journal?${params.toString()}`;
}

/** Журнал за период сводки, только закрытые: единственный список, сходящийся с ней. */
export function journalClosedLink(): string {
  return journalPeriodLink({ [PARAM.status]: 'closed' });
}

/** Закрытые сделки периода, у которых нет рефлексии. */
export function journalUnreflectedLink(): string {
  return journalPeriodLink({ [PARAM.status]: 'closed', [PARAM.reflection]: 'none' });
}

/** Все открытые позиции — без периода: открытая позиция к периоду не привязана. */
export function journalOpenLink(): string {
  return `/journal?${new URLSearchParams({ [PARAM.status]: 'open' }).toString()}`;
}

/**
 * Ссылка в журнал за один торговый день. Границы приходят из ответа календаря и
 * подставляются как есть — второго правила дня на клиенте нет (SPEC.md 5.4).
 *
 * `status=closed` обязателен: без него в список приедут ещё и позиции, открытые внутри
 * этого окна, и сумма колонки разойдётся с числом в ячейке (DoD S2-09).
 */
export function journalDayLink(startsAt: string, endsAt: string): string {
  const params = new URLSearchParams({
    [PARAM.from]: startsAt,
    [PARAM.to]: endsAt,
    [PARAM.status]: 'closed',
  });
  return `/journal?${params.toString()}`;
}
