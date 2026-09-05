/**
 * Сессия пользователя. Один источник правды — кэш запроса `/api/v1/auth/me`;
 * компоненты читают его через `useSession()` и своей копии не держат.
 */
import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';

import { api, setUnauthorizedHandler, unwrap, unwrapEmpty } from '@/api/client';
import { ApiRequestError } from '@/api/errors';
import type { components } from '@/api/schema';

export type SessionUser = components['schemas']['UserResponse'];

export const SESSION_QUERY_KEY = ['auth', 'me'] as const;
/** Отметка «сессия оборвалась» — чтобы /login объяснил, почему человек здесь. */
export const SESSION_EXPIRED_QUERY_KEY = ['auth', 'session-expired'] as const;

const UNAUTHORIZED_STATUS = 401;

async function fetchSession(): Promise<SessionUser | null> {
  try {
    return await unwrap(api.GET('/api/v1/auth/me'));
  } catch (error) {
    // 401 на /me — это «не вошёл», штатный ответ, а не сбой.
    if (error instanceof ApiRequestError && error.status === UNAUTHORIZED_STATUS) {
      return null;
    }
    throw error;
  }
}

export function useSession() {
  return useQuery({
    queryKey: SESSION_QUERY_KEY,
    queryFn: fetchSession,
    staleTime: 30_000,
    // 401 сюда не доходит — он возвращается как `null`. Значит, ошибка здесь всегда
    // «не смогли спросить»: сеть моргнула или api отвечает 5xx. Один повтор отделяет
    // такой случай от настоящего выхода из системы.
    retry: 1,
    // Перекрывает общий `refetchOnWindowFocus: false`: сессия может истечь или быть
    // погашена на сервере, пока вкладка лежит в фоне, и заметить это должен клиент.
    // Без этого экраны рисуются под уже мёртвой сессией, пока не уйдёт первый запрос.
    refetchOnWindowFocus: true,
  });
}

/**
 * Пользователь из кэша сессии без собственного запроса: `enabled: false` подписывает
 * компонент на изменения кэша, но сам ничего не грузит. Нужно там, где данные профиля
 * лишь украшают экран, — например, таймзона для дат на `/dev/outbox`, куда приходят
 * ещё не войдя, и лишний запрос `/auth/me` там был бы запросом ради оформления.
 */
export function useCachedSessionUser(): SessionUser | null | undefined {
  const { data } = useQuery({
    queryKey: SESSION_QUERY_KEY,
    queryFn: fetchSession,
    enabled: false,
  });
  return data;
}

export function useRequestCode() {
  return useMutation({
    mutationFn: (email: string) =>
      unwrap(api.POST('/api/v1/auth/request-code', { body: { email } })),
  });
}

export function useVerifyCode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (variables: { email: string; code: string }) =>
      unwrap(api.POST('/api/v1/auth/verify', { body: variables })),
    onSuccess: (user) => {
      queryClient.setQueryData<SessionUser | null>(SESSION_QUERY_KEY, user);
      queryClient.removeQueries({ queryKey: SESSION_EXPIRED_QUERY_KEY });
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrapEmpty(api.POST('/api/v1/auth/logout')),
    // Ответ 204 идемпотентен, поэтому даже неудачный выход обнуляет сессию на клиенте:
    // держать экран под пользователем, который нажал «Выйти», нельзя.
    onSettled: () => {
      queryClient.setQueryData<SessionUser | null>(SESSION_QUERY_KEY, null);
      queryClient.removeQueries({ queryKey: SESSION_EXPIRED_QUERY_KEY });
    },
  });
}

/**
 * Единственная точка обработки 401 (тикет S0-07, развилка 5): любой ответ 401 обнуляет
 * сессию, а увод на /login делает `RequireAuth`. Компоненты 401 не разбирают.
 */
export function installUnauthorizedBridge(queryClient: QueryClient): () => void {
  setUnauthorizedHandler(() => {
    if (queryClient.getQueryData<SessionUser | null>(SESSION_QUERY_KEY)) {
      queryClient.setQueryData(SESSION_EXPIRED_QUERY_KEY, true);
    }
    queryClient.setQueryData<SessionUser | null>(SESSION_QUERY_KEY, null);
  });
  return () => setUnauthorizedHandler(null);
}
