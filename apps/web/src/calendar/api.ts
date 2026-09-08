/**
 * Календарь — `GET /journal/calendar` (SPEC.md 5.4). Один модуль на двух потребителей:
 * экран `/calendar` (`S2-09`) и календарь-мини дашборда (`S2-10`).
 *
 * Двух чтений одного ответа быть не должно: разойдясь, они показали бы человеку в мини
 * одно число, а на экране календаря другое — и разницу нельзя было бы объяснить ничем,
 * кроме бага. Поэтому типы, ключ кэша и параметры запроса живут здесь, а экраны
 * различаются только тем, как рисуют один и тот же ответ.
 *
 * Числа приходят готовыми: день, его границы и суммы считает сервер (`docs/metrics.md`
 * §5). Клиент их не пересчитывает — он их складывает в итоги недели и месяца, и только
 * потому, что дни месяца получены целиком (`calendar/totals.ts`).
 */
import { useQuery } from '@tanstack/react-query';

import { accountIdsParam } from '@/accounts/selection';
import { api, unwrap } from '@/api/client';
import type { components, operations } from '@/api/schema';

export type CalendarMonth = components['schemas']['CalendarResponse'];
export type CalendarDay = components['schemas']['CalendarDay'];
export type CalendarAccountDay = components['schemas']['CalendarAccountDay'];

export type CalendarQueryParams =
  operations['read_calendar_api_v1_journal_calendar_get']['parameters']['query'];

export const CALENDAR_QUERY_KEY = ['journal', 'calendar'] as const;

/**
 * Параметры запроса месяца. `month` — `yyyy-MM` в зоне пользователя; счета приходят из
 * глобального переключателя (SPEC.md 9.2), и смена выбора меняет ключ запроса — экран
 * обновляется без перезагрузки.
 */
export function calendarParams(month: string, accountIds: readonly string[]): CalendarQueryParams {
  const params: CalendarQueryParams = { month };
  const ids = accountIdsParam(accountIds);
  if (ids !== undefined) {
    params.account_ids = ids;
  }
  return params;
}

export function useCalendarMonth(params: CalendarQueryParams, enabled: boolean) {
  return useQuery({
    queryKey: [...CALENDAR_QUERY_KEY, params],
    queryFn: () => unwrap(api.GET('/api/v1/journal/calendar', { params: { query: params } })),
    enabled,
  });
}
