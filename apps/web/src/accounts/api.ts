/**
 * Счета — ресурс `/accounts` (SPEC.md 5.2). Типы берутся из сгенерированной схемы:
 * рукописных описаний тел и ответов здесь нет.
 *
 * Отдельного `GET /accounts/{id}` в контракте нет намеренно — счетов у пользователя
 * единицы и список отдаётся целиком. Поэтому карточка одного счёта читает тот же список,
 * а не заводит свой запрос: два источника одной сущности разошлись бы в кэше.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseMutationResult,
} from '@tanstack/react-query';
import { useCallback } from 'react';

import { api, unwrap, unwrapEmpty } from '@/api/client';
import type { components } from '@/api/schema';

export type Account = components['schemas']['AccountResponse'];
export type AccountCreate = components['schemas']['AccountCreateRequest'];
export type AccountUpdate = components['schemas']['AccountUpdateRequest'];
export type AccountStatus = Account['status'];
export type AccountPlatform = Account['platform'];
export type SyncNowResult = components['schemas']['SyncNowResponse'];
export type SyncRun = components['schemas']['SyncRunResponse'];

export const ACCOUNTS_QUERY_KEY = ['accounts'] as const;

export function accountsQueryKey(includeArchived: boolean) {
  return [...ACCOUNTS_QUERY_KEY, { includeArchived }] as const;
}

export function syncRunsQueryKey(accountId: string) {
  return [...ACCOUNTS_QUERY_KEY, accountId, 'sync-runs'] as const;
}

export function useAccounts(includeArchived: boolean) {
  return useQuery({
    queryKey: accountsQueryKey(includeArchived),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/accounts', {
          params: { query: includeArchived ? { include_archived: true } : {} },
        }),
      ),
  });
}

export function useSyncRuns(accountId: string) {
  return useQuery({
    queryKey: syncRunsQueryKey(accountId),
    queryFn: () =>
      unwrap(
        api.GET('/api/v1/accounts/{account_id}/sync-runs', {
          params: { path: { account_id: accountId } },
        }),
      ),
  });
}

/**
 * Любая правка счёта меняет и его карточку, и состав списка (архив уводит счёт из
 * выдачи по умолчанию), поэтому обновляется весь раздел, а не одна запись.
 */
function invalidateAccounts(client: QueryClient): Promise<void> {
  return client.invalidateQueries({ queryKey: ACCOUNTS_QUERY_KEY });
}

const CREATE_MUTATION_KEY = [...ACCOUNTS_QUERY_KEY, 'create'] as const;

function updateMutationKey(accountId: string) {
  return [...ACCOUNTS_QUERY_KEY, accountId, 'update'] as const;
}

/**
 * Тело запроса переживает сам запрос: `variables` лежат в кэше мутаций, пока их не заберёт
 * сборщик мусора (`gcTime` — пять минут после размонтирования), а наблюдатель отдаёт ту же
 * копию наружу как `mutation.variables`. `QueryClient` достижим из дерева компонентов, то
 * есть достижимы и обе копии, — а в теле создания и правки счёта лежит открытый пароль
 * инвестора. Поэтому обе стираются сразу после успеха, а не по таймеру.
 */
function forgetMutation(client: QueryClient, mutationKey: readonly unknown[]): void {
  const cache = client.getMutationCache();
  for (const stored of cache.findAll({ mutationKey, exact: true })) {
    cache.remove(stored);
  }
}

/** Мутация, тело которой нельзя оставлять в памяти страницы. */
export type SecretMutation<TData, TVariables> = UseMutationResult<TData, Error, TVariables> & {
  /** Стирает тело запроса из наблюдателя и из кэша мутаций; см. `forgetMutation`. */
  forget: () => void;
};

export function useCreateAccount(): SecretMutation<Account, AccountCreate> {
  const client = useQueryClient();
  const mutation = useMutation({
    mutationKey: CREATE_MUTATION_KEY,
    mutationFn: (body: AccountCreate) => unwrap(api.POST('/api/v1/accounts', { body })),
    onSuccess: () => invalidateAccounts(client),
  });
  const { reset } = mutation;
  const forget = useCallback(() => {
    reset();
    forgetMutation(client, CREATE_MUTATION_KEY);
  }, [client, reset]);
  return { ...mutation, forget };
}

export function useUpdateAccount(accountId: string): SecretMutation<Account, AccountUpdate> {
  const client = useQueryClient();
  const mutation = useMutation({
    mutationKey: updateMutationKey(accountId),
    mutationFn: (body: AccountUpdate) =>
      unwrap(
        api.PATCH('/api/v1/accounts/{account_id}', {
          params: { path: { account_id: accountId } },
          body,
        }),
      ),
    onSuccess: () => invalidateAccounts(client),
  });
  const { reset } = mutation;
  const forget = useCallback(() => {
    reset();
    forgetMutation(client, updateMutationKey(accountId));
  }, [accountId, client, reset]);
  return { ...mutation, forget };
}

export function useSetAccountPaused(accountId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (paused: boolean) =>
      unwrap(
        paused
          ? api.POST('/api/v1/accounts/{account_id}/pause', {
              params: { path: { account_id: accountId } },
            })
          : api.POST('/api/v1/accounts/{account_id}/resume', {
              params: { path: { account_id: accountId } },
            }),
      ),
    onSuccess: () => invalidateAccounts(client),
  });
}

export function useArchiveAccount(accountId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/accounts/{account_id}/archive', {
          params: { path: { account_id: accountId } },
        }),
      ),
    onSuccess: () => invalidateAccounts(client),
  });
}

export function useDeleteAccount(accountId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrapEmpty(
        api.DELETE('/api/v1/accounts/{account_id}', {
          params: { path: { account_id: accountId } },
        }),
      ),
    onSuccess: () => invalidateAccounts(client),
  });
}

/**
 * `202`: сервер записал просьбу, синк выполнит коллектор (SPEC.md 5.2). Ответ обновляет и
 * карточку — `last_heartbeat_at` в нём свежее того, что лежит в списке.
 */
export function useSyncNow(accountId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/v1/accounts/{account_id}/sync-now', {
          params: { path: { account_id: accountId } },
        }),
      ),
    onSuccess: () => invalidateAccounts(client),
  });
}
