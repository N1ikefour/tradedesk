/**
 * Профиль пользователя — ресурс `/users/me` (GET и PATCH). Форма ответа та же, что у
 * `/auth/me`: в схеме это один компонент `UserResponse`, поэтому и типа здесь два раза
 * не заводится.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import {
  SESSION_QUERY_KEY,
  useCachedSessionUser,
  useSession,
  type SessionUser,
} from '@/auth/session';
import { browserTimeZone, isKnownTimeZone } from '@/lib/time-zones';

export type Profile = components['schemas']['UserResponse'];
export type ProfileUpdate = components['schemas']['UserUpdateRequest'];

export const PROFILE_QUERY_KEY = ['users', 'me'] as const;

export function useProfile() {
  return useQuery({
    queryKey: PROFILE_QUERY_KEY,
    queryFn: () => unwrap(api.GET('/api/v1/users/me')),
  });
}

/**
 * PATCH отдаёт уже применённые значения, поэтому ответ кладётся в кэш как есть —
 * перечитывать профиль отдельным запросом нечего. Тем же ответом обновляется сессия:
 * это один и тот же пользователь, и разъехавшиеся копии показали бы в шапке одно,
 * а на экране настроек другое.
 */
export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ProfileUpdate) => unwrap(api.PATCH('/api/v1/users/me', { body })),
    onSuccess: (profile) => {
      queryClient.setQueryData<Profile>(PROFILE_QUERY_KEY, profile);
      queryClient.setQueryData<SessionUser | null>(SESSION_QUERY_KEY, profile);
    },
  });
}

/**
 * Зона профиля, если движок её знает. Иначе — зона компьютера: наборы имён IANA у
 * браузера и у сервера расходятся по псевдонимам, и падать на этом нельзя.
 */
function knownOrBrowserTimeZone(timeZone: string | undefined): string {
  return timeZone !== undefined && isKnownTimeZone(timeZone) ? timeZone : browserTimeZone();
}

/**
 * Таймзона показа времени на экранах под `RequireAuth`. Гард рисует их только с
 * загруженной сессией, поэтому здесь это действительно зона пользователя (SPEC.md 9.4).
 */
export function useProfileTimeZone(): string {
  const { data } = useSession();
  return knownOrBrowserTimeZone(data?.timezone);
}

/**
 * Час начала торгового дня из профиля (SPEC.md 3). Ноль — не «полночь по умолчанию», а
 * значение, с которым заводится пользователь: сервер хранит его обязательным.
 */
export function useProfileDayBoundaryHour(): number {
  const { data } = useSession();
  return data?.day_boundary_hour ?? 0;
}

/**
 * Таймзона показа времени там, где сессии может не быть вовсе: `/dev/outbox` открыт до
 * входа, и запрос `/auth/me` ради оформления дат там был бы лишним. Смотрит кэш сессии
 * и ничего не грузит; пустой кэш означает зону компьютера.
 *
 * Имя обещает ровно это — зону показа, а не зону пользователя: пустой кэш здесь штатен,
 * и вызывающий не должен принимать результат за настройку профиля.
 */
export function useDisplayTimeZone(): string {
  const user = useCachedSessionUser();
  return knownOrBrowserTimeZone(user?.timezone);
}
