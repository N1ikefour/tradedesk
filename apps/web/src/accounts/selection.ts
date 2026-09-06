/**
 * Глобальный выбор счетов — SPEC.md 9.2. Единственное состояние приложения, которое
 * живёт в `zustand`: оно сквозное (журнал, календарь, дашборд смотрят на один и тот же
 * выбор), переживает переход между экранами и обязано пережить перезагрузку.
 *
 * Всё остальное состояние остаётся локальным или в адресе — фильтры журнала, например,
 * лежат в URL, потому что ссылкой на отфильтрованный список делятся, а выбором счетов
 * нет: это настройка рабочего места, а не описание того, что на экране.
 *
 * Пресеты «Все реальные» и предупреждение «демо и реал вместе» — `S2-11`. Здесь есть
 * только форма состояния под них, чтобы хранилище не пришлось переучивать задним числом
 * вместе с уже сохранёнными у людей значениями.
 */
import { useMemo } from 'react';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import { useAccounts, type Account } from '@/accounts/api';

export const SELECTION_STORAGE_KEY = 'td.accountSelection.v1';

export type AccountSelectionMode = 'single' | 'multi' | 'all_real' | 'all';

export type AccountSelection = {
  readonly mode: AccountSelectionMode;
  readonly ids: readonly string[];
};

type SelectionActions = {
  /** Явный список счетов. Пустой список означает «все»: выбор без единого счёта — не выбор. */
  readonly selectIds: (ids: readonly string[]) => void;
  readonly toggleId: (id: string) => void;
  readonly selectAll: () => void;
};

const INITIAL: AccountSelection = { mode: 'all', ids: [] };

function fromIds(ids: readonly string[]): AccountSelection {
  if (ids.length === 0) {
    return INITIAL;
  }
  return { mode: ids.length === 1 ? 'single' : 'multi', ids: [...ids] };
}

/**
 * `localStorage` бросает исключение, а не возвращает пустоту, когда браузер запретил
 * хранилище сайту. Выбор счетов не та вещь, ради которой приложение должно не открыться.
 */
const safeStorage = createJSONStorage(() => ({
  getItem: (name: string): string | null => {
    try {
      return window.localStorage.getItem(name);
    } catch {
      return null;
    }
  },
  setItem: (name: string, value: string): void => {
    try {
      window.localStorage.setItem(name, value);
    } catch {
      // Выбор просто не переживёт перезагрузку — это лучше, чем упавший экран.
    }
  },
  removeItem: (name: string): void => {
    try {
      window.localStorage.removeItem(name);
    } catch {
      // См. выше.
    }
  },
}));

const MODES: readonly AccountSelectionMode[] = ['single', 'multi', 'all_real', 'all'];

/**
 * Значение из хранилища — чужой ввод: его правит рука, старая версия приложения и другая
 * вкладка. Всё, что не разбирается, заменяется выбором «все»: он безопасен, потому что
 * ничего не прячет.
 */
function sanitize(raw: unknown): AccountSelection {
  if (typeof raw !== 'object' || raw === null) {
    return INITIAL;
  }
  const value = raw as { mode?: unknown; ids?: unknown };
  const mode = MODES.find((candidate) => candidate === value.mode);
  const ids = Array.isArray(value.ids)
    ? value.ids.filter((id): id is string => typeof id === 'string' && id !== '')
    : [];
  if (mode === undefined) {
    return fromIds(ids);
  }
  if (mode === 'all' || mode === 'all_real') {
    return { mode, ids: [] };
  }
  return fromIds(ids);
}

export const useAccountSelectionStore = create<AccountSelection & SelectionActions>()(
  persist(
    (set, get) => ({
      ...INITIAL,
      selectIds: (ids) => set(fromIds(ids)),
      toggleId: (id) => {
        const current = get();
        const explicit = current.mode === 'single' || current.mode === 'multi';
        const ids = explicit ? current.ids : [];
        set(fromIds(ids.includes(id) ? ids.filter((value) => value !== id) : [...ids, id]));
      },
      selectAll: () => set(INITIAL),
    }),
    {
      name: SELECTION_STORAGE_KEY,
      storage: safeStorage,
      partialize: (state): AccountSelection => ({ mode: state.mode, ids: state.ids }),
      merge: (persisted, current) => ({ ...current, ...sanitize(persisted) }),
    },
  ),
);

export function useAccountSelection(): AccountSelection {
  const mode = useAccountSelectionStore((state) => state.mode);
  const ids = useAccountSelectionStore((state) => state.ids);
  return useMemo(() => ({ mode, ids }), [mode, ids]);
}

export type ResolvedAccountIds = {
  /** То, что уходит в `account_ids`. Пустой список — «все», параметр не отправляется. */
  readonly ids: readonly string[];
  /** Можно ли уже спрашивать список: непроверенный выбор счетов посылать нельзя. */
  readonly ready: boolean;
};

const ALL: ResolvedAccountIds = { ids: [], ready: true };

/**
 * Выбор → `account_ids`. Счёт мог быть удалён или архивирован в другой вкладке, а выбор
 * при этом остался в `localStorage`: сохранённый id тогда указывает в никуда, и сервер
 * отвечает `404 account_not_found` — то есть красной ошибкой вместо журнала. Поэтому
 * неизвестные id отбрасываются, а выбор, от которого ничего не осталось, читается как
 * «все».
 *
 * Пока список счетов не приехал, проверить сохранённый выбор нечем, и запрос ждёт. Это
 * стоит одного обращения к сети перед первым показом журнала — но только тем, у кого
 * выбор не «все»; сам список счетов в это время уже грузится для шапки. Обратный
 * порядок — «спросить сразу, разобраться потом» — проверялся в браузере и давал ровно
 * ту ошибку, от которой защищает отбрасывание: первый запрос уходил со снятым счётом и
 * возвращал 404.
 */
export function resolveSelection(
  selection: AccountSelection,
  accounts: readonly Account[] | undefined,
): ResolvedAccountIds {
  if (selection.mode === 'all') {
    return ALL;
  }
  if (accounts === undefined) {
    return { ids: [], ready: false };
  }
  if (selection.mode === 'all_real') {
    return {
      ids: accounts.filter((account) => !account.is_demo).map((account) => account.id),
      ready: true,
    };
  }
  const known = new Set(accounts.map((account) => account.id));
  const kept = selection.ids.filter((id) => known.has(id));
  return kept.length === 0 ? ALL : { ids: kept, ready: true };
}

/**
 * `account_ids` для запросов экрана (SPEC.md 9.2). Список счетов берётся из того же
 * запроса, что кормит переключатель в шапке, — второго обращения к сети здесь нет.
 */
export function useAccountIds(): ResolvedAccountIds {
  const selection = useAccountSelection();
  const accounts = useAccounts(false);
  const items = accounts.data?.items;
  const failed = accounts.isError;
  return useMemo(() => {
    if (items === undefined && failed) {
      // Список счетов не пришёл — но это не повод не показывать журнал: «все счета»
      // ровно то, что видно без переключателя.
      return ALL;
    }
    return resolveSelection(selection, items);
  }, [selection, items, failed]);
}

/** `account_ids=uuid,uuid` — формат SPEC.md 5.1. Пустой выбор параметра не даёт. */
export function accountIdsParam(ids: readonly string[]): string | undefined {
  return ids.length === 0 ? undefined : ids.join(',');
}
