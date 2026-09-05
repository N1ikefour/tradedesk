/**
 * Профиль пользователя — ресурс `/users/me` (GET и PATCH). Форма ответа та же, что у
 * `/auth/me`: в схеме это один компонент `UserResponse`, поэтому и типа здесь два раза
 * не заводится.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, unwrap } from '@/api/client';
import type { components } from '@/api/schema';
import { SESSION_QUERY_KEY, useCachedSessionUser, type SessionUser } from '@/auth/session';
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
 * Таймзона, в которой показывается время. Профиль — источник правды (SPEC.md 9.4);
 * пока он не загружен или зона незнакома движку, остаётся зона компьютера.
 */
export function useUserTimeZone(): string {
  const user = useCachedSessionUser();
  const timeZone = user?.timezone;
  return timeZone !== undefined && isKnownTimeZone(timeZone) ? timeZone : browserTimeZone();
}
