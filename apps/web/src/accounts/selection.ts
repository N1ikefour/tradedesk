/**
 * Глобальный выбор счетов — SPEC.md 9.2. Единственное состояние приложения, которое
 * живёт в `zustand`: оно сквозное (журнал, календарь, дашборд смотрят на один и тот же
 * выбор), переживает переход между экранами и обязано пережить перезагрузку.
 *
 * Всё остальное состояние остаётся локальным или в адресе — фильтры журнала, например,
 * лежат в URL, потому что ссылкой на отфильтрованный список делятся, а выбором счетов
 * нет: это настройка рабочего места, а не описание того, что на экране.
 *
 * Режим `all_real` — правило, а не список: он разворачивается по загруженным счетам на
 * каждый запрос. Поэтому счёт, заведённый или перекрашенный в демо после выбора пресета,
 * попадает в выборку или уходит из неё сам, без переспрашивания человека.
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
  readonly selectAllReal: () => void;
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
      selectAllReal: () => set({ mode: 'all_real', ids: [] }),
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
  /**
   * Выбор не совпал ни с одним счётом. Отдельный признак нужен потому, что пустой
   * `ids` в контракте `SPEC.md` 5.1 означает противоположное — «все счета».
   */
  readonly empty: boolean;
};

const ALL: ResolvedAccountIds = { ids: [], ready: true, empty: false };

/** Правило, под которое не подошёл ни один счёт. Списку нечего показывать. */
const NOTHING: ResolvedAccountIds = { ids: [], ready: true, empty: true };

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
    return { ids: [], ready: false, empty: false };
  }
  if (selection.mode === 'all_real') {
    // «Все реальные» — правило, а не список: не подошло ни одного счёта — значит
    // показывать нечего. Молчаливый переход к «всем» показал бы здесь ровно то, что
    // выбор исключает, — демо-сделки под видом реальных.
    const real = accounts.filter((account) => !account.is_demo).map((account) => account.id);
    return real.length === 0 ? NOTHING : { ids: real, ready: true, empty: false };
  }
  const known = new Set(accounts.map((account) => account.id));
  const kept = selection.ids.filter((id) => known.has(id));
  // Явный список — не правило: он мог протухнуть целиком, пока счета правили в другой
  // вкладке, и «все» здесь безопаснее пустого экрана, потому что ничего не прячет.
  return kept.length === 0 ? ALL : { ids: kept, ready: true, empty: false };
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

/** Счета, попавшие в выборку. Пустой `ids` при `empty = false` — это «все». */
function selectedAccounts(
  resolved: ResolvedAccountIds,
  accounts: readonly Account[],
): readonly Account[] {
  if (!resolved.ready || resolved.empty) {
    return [];
  }
  return resolved.ids.length === 0
    ? accounts
    : accounts.filter((account) => resolved.ids.includes(account.id));
}

/**
 * Показывать ли пресет «Все реальные» (SPEC.md 9.2).
 *
 * У первого пользователя все четыре счёта демо, и пресет дал бы ему пустой экран по
 * нажатию — то есть выглядел бы поломкой ровно там, где он и работает как задумано.
 * Обратный край не лучше: без единого демо-счёта «Все реальные» и «Все» — одна и та же
 * выборка, и две кнопки с одним действием заставляют искать между ними разницу.
 *
 * Поэтому пресет — не постоянный элемент, а ответ на вопрос «какие из них смотреть»,
 * и появляется он ровно тогда, когда вопрос есть: счета обоих видов сразу. Выключенная
 * кнопка тут хуже отсутствующей: она обещает действие и требует объяснения, почему его
 * нет, — а объяснять нечего, реальных счетов просто ни одного.
 *
 * Исключение — уже выбранный `all_real`: значение переживает архивацию последнего
 * реального счёта и приезжает из другой вкладки. Спрятать пресет под ним значило бы
 * оставить человека с пустым журналом и без единого способа увидеть, чем он пуст.
 */
export function showsAllRealPreset(
  selection: AccountSelection,
  accounts: readonly Account[],
): boolean {
  if (selection.mode === 'all_real') {
    return true;
  }
  return (
    accounts.some((account) => account.is_demo) && accounts.some((account) => !account.is_demo)
  );
}

/**
 * В выборке демо и реал одновременно (SPEC.md 9.2, §14 «Демо + реал в сводке»).
 *
 * Считается по фактическому составу выборки, а не по имени пресета: смешать их вручную
 * галочками так же легко, как пресетом «Все», и результат тот же — сумма, в которой
 * тренировочные деньги сложены с настоящими. Обратная сторона того же правила важнее:
 * у человека с одними демо-счетами пресет «Все» ничего не смешивает, и предупреждение,
 * висящее там постоянно, за неделю перестало бы читаться.
 */
export function mixesDemoAndReal(
  resolved: ResolvedAccountIds,
  accounts: readonly Account[],
): boolean {
  const chosen = selectedAccounts(resolved, accounts);
  return chosen.some((account) => account.is_demo) && chosen.some((account) => !account.is_demo);
}

/**
 * Попадёт ли только что заведённый счёт в текущую выборку.
 *
 * Спрашивается сразу после создания, когда список счетов ещё перезапрашивается, поэтому
 * новый счёт добавляется к известным здесь же: иначе пресет «Все реальные» ответил бы
 * «нет» про реальный счёт просто потому, что его в списке пока нет.
 */
export function coversNewAccount(
  selection: AccountSelection,
  accounts: readonly Account[],
  created: Account,
): boolean {
  const known = accounts.some((account) => account.id === created.id)
    ? accounts
    : [...accounts, created];
  return selectedAccounts(resolveSelection(selection, known), known).some(
    (account) => account.id === created.id,
  );
}
