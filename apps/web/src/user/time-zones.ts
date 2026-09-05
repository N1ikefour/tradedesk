/**
 * Имена таймзон для меню — `GET /api/v1/users/timezones`.
 *
 * Источник именно серверный, а не `Intl.supportedValuesOf`: отдаёт список тот же код,
 * что проверяет `PATCH /users/me`, поэтому непринимаемого имени в меню быть не может.
 * Раньше меню строилось по набору движка, и 18 его имён сервер отвергал `400` — для
 * части стран это был единственный пункт их зоны.
 */
import { useQuery } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';

export const TIME_ZONES_QUERY_KEY = ['users', 'timezones'] as const;

/**
 * Свежесть держит `ETag`, а не этот таймер: ответ помечен `private, no-cache`, браузер
 * сам переспрашивает условным запросом и на неизменившемся списке получает 304 без
 * девяти килобайт тела. Значит `staleTime` решает лишь, как часто вообще беспокоить
 * сеть, и может быть большим. `gcTime` тот же: уход с экрана и возврат не должны
 * возвращать человека к состоянию загрузки.
 */
const LIST_LIFETIME_MS = 24 * 60 * 60 * 1000;

export function useTimeZoneNames() {
  return useQuery({
    queryKey: TIME_ZONES_QUERY_KEY,
    queryFn: async (): Promise<readonly string[]> => {
      const response = await unwrap(api.GET('/api/v1/users/timezones'));
      return response.items;
    },
    staleTime: LIST_LIFETIME_MS,
    gcTime: LIST_LIFETIME_MS,
  });
}
