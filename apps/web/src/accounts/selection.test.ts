import { beforeEach, describe, expect, it } from 'vitest';

import type { Account } from '@/accounts/api';
import {
  SELECTION_STORAGE_KEY,
  coversNewAccount,
  mixesDemoAndReal,
  resolveSelection,
  showsAllRealPreset,
  useAccountSelectionStore,
} from '@/accounts/selection';

const FIRST = '0199a2b0-0000-7000-8000-0000000000a1';
const SECOND = '0199a2b0-0000-7000-8000-0000000000a2';
const GONE = '0199a2b0-0000-7000-8000-00000000dead';

function account(id: string, isDemo: boolean): Account {
  return {
    id,
    label: `Счёт ${id.slice(-2)}`,
    is_demo: isDemo,
    color: '#2563eb',
    platform: 'mt5',
    broker: null,
    server: 'Broker-Demo',
    login: 5_001_234,
    currency: 'USD',
    account_type: null,
    server_utc_offset_minutes: null,
    status: 'pending',
    status_message: null,
    last_sync_at: null,
    last_heartbeat_at: null,
    collector_id: null,
    sort_order: 0,
    created_at: '2026-09-01T10:00:00Z',
    positions_count: 0,
  };
}

const ACCOUNTS = [account(FIRST, false), account(SECOND, true)];

beforeEach(() => {
  window.localStorage.clear();
  useAccountSelectionStore.setState({ mode: 'all', ids: [] });
});

describe('resolveSelection', () => {
  it('«все» не даёт ни одного id: параметра в запросе не будет', () => {
    expect(resolveSelection({ mode: 'all', ids: [] }, ACCOUNTS)).toEqual({
      ids: [],
      ready: true,
      empty: false,
    });
  });

  it('удалённый счёт выпадает из выбора, а не роняет журнал в 404', () => {
    const resolved = resolveSelection({ mode: 'multi', ids: [FIRST, GONE] }, ACCOUNTS);

    expect(resolved.ids).toEqual([FIRST]);
  });

  it('выбор, от которого ничего не осталось, читается как «все»', () => {
    expect(resolveSelection({ mode: 'single', ids: [GONE] }, ACCOUNTS).ids).toEqual([]);
  });

  it('без списка счетов запрос ждёт: непроверенный id вернул бы 404 вместо журнала', () => {
    expect(resolveSelection({ mode: 'single', ids: [FIRST] }, undefined)).toEqual({
      ids: [],
      ready: false,
      empty: false,
    });
    expect(resolveSelection({ mode: 'all_real', ids: [] }, undefined)).toEqual({
      ids: [],
      ready: false,
      empty: false,
    });
  });

  it('«все» не ждёт ничего: проверять там нечего', () => {
    expect(resolveSelection({ mode: 'all', ids: [] }, undefined).ready).toBe(true);
  });

  it('пресет «все реальные» разворачивается по загруженному списку', () => {
    expect(resolveSelection({ mode: 'all_real', ids: [] }, ACCOUNTS)).toEqual({
      ids: [FIRST],
      ready: true,
      empty: false,
    });
  });

  it('«все реальные» без единого реального счёта — пусто, а не «все»', () => {
    // Пустой `ids` в контракте означает «все счета», поэтому без отдельного признака
    // выбор «Все реальные» показал бы демо-сделки под видом реальных.
    const demoOnly = [account(SECOND, true)];

    expect(resolveSelection({ mode: 'all_real', ids: [] }, demoOnly)).toEqual({
      ids: [],
      ready: true,
      empty: true,
    });
    expect(resolveSelection({ mode: 'all_real', ids: [] }, [])).toEqual({
      ids: [],
      ready: true,
      empty: true,
    });
  });

  it('протухший явный список — это «все», а не пусто: он не правило, а остаток', () => {
    expect(resolveSelection({ mode: 'single', ids: [GONE] }, ACCOUNTS)).toEqual({
      ids: [],
      ready: true,
      empty: false,
    });
  });
});

describe('пресет «Все реальные»', () => {
  const DEMO_ONLY = [account(SECOND, true)];
  const REAL_ONLY = [account(FIRST, false)];

  it('показывается только там, где счета обоих видов', () => {
    expect(showsAllRealPreset({ mode: 'all', ids: [] }, ACCOUNTS)).toBe(true);
  });

  it('прячется при одних демо-счетах: нажатие дало бы пустой экран', () => {
    expect(showsAllRealPreset({ mode: 'all', ids: [] }, DEMO_ONLY)).toBe(false);
  });

  it('прячется при одних реальных: он равен «Все», а две кнопки с одним действием мешают', () => {
    expect(showsAllRealPreset({ mode: 'all', ids: [] }, REAL_ONLY)).toBe(false);
  });

  it('остаётся видимым, если уже выбран: иначе из него нечем выйти', () => {
    expect(showsAllRealPreset({ mode: 'all_real', ids: [] }, DEMO_ONLY)).toBe(true);
    expect(showsAllRealPreset({ mode: 'all_real', ids: [] }, [])).toBe(true);
  });

  it('пустой список счетов пресета не показывает', () => {
    expect(showsAllRealPreset({ mode: 'all', ids: [] }, [])).toBe(false);
  });
});

describe('смешение демо и реала', () => {
  const ALL = { ids: [], ready: true, empty: false } as const;

  it('«все счета» при счетах обоих видов — это смешение', () => {
    expect(mixesDemoAndReal(ALL, ACCOUNTS)).toBe(true);
  });

  it('«все счета» при одних демо ничего не смешивает', () => {
    expect(mixesDemoAndReal(ALL, [account(SECOND, true)])).toBe(false);
  });

  it('считается по составу выборки, а не по имени пресета', () => {
    expect(mixesDemoAndReal({ ids: [FIRST, SECOND], ready: true, empty: false }, ACCOUNTS)).toBe(
      true,
    );
    expect(mixesDemoAndReal({ ids: [SECOND], ready: true, empty: false }, ACCOUNTS)).toBe(false);
  });

  it('пустая и непроверенная выборка предупреждения не даёт: смешивать нечего', () => {
    expect(mixesDemoAndReal({ ids: [], ready: true, empty: true }, ACCOUNTS)).toBe(false);
    expect(mixesDemoAndReal({ ids: [], ready: false, empty: false }, ACCOUNTS)).toBe(false);
  });
});

describe('новый счёт и текущий выбор', () => {
  const CREATED = account(GONE, true);
  const CREATED_REAL = account(GONE, false);

  it('при «всех счетах» новый счёт в выборке', () => {
    expect(coversNewAccount({ mode: 'all', ids: [] }, ACCOUNTS, CREATED)).toBe(true);
  });

  it('при «всех реальных» демо-счёт в выборку не попадает, а реальный попадает', () => {
    // Список счетов ещё перезапрашивается, нового в нём нет — ответ обязан быть верным и
    // до его прихода.
    expect(coversNewAccount({ mode: 'all_real', ids: [] }, ACCOUNTS, CREATED)).toBe(false);
    expect(coversNewAccount({ mode: 'all_real', ids: [] }, ACCOUNTS, CREATED_REAL)).toBe(true);
  });

  it('при выборе одного счёта новый в выборку не входит', () => {
    expect(coversNewAccount({ mode: 'single', ids: [FIRST] }, ACCOUNTS, CREATED)).toBe(false);
  });

  it('протухший выбор читается как «все», и новый счёт в нём виден', () => {
    expect(coversNewAccount({ mode: 'single', ids: ['0199-нет-такого'] }, ACCOUNTS, CREATED)).toBe(
      true,
    );
  });

  /**
   * Без списка счетов проверить, не протух ли явный выбор, нечем. Пустой список на его
   * месте прочитал бы любой явный выбор как «все» и ответил бы «счёт уже в выборе» тому,
   * у кого выбран один счёт, — то есть спрятал бы кнопку, которой это исправляют.
   */
  it('без списка счетов явный выбор считается живым, а не протухшим', () => {
    expect(coversNewAccount({ mode: 'single', ids: [FIRST] }, undefined, CREATED)).toBe(false);
    expect(coversNewAccount({ mode: 'multi', ids: [FIRST, SECOND] }, undefined, CREATED)).toBe(
      false,
    );
  });

  it('без списка счетов правила отвечают сами: «все» — да, «все реальные» — по виду счёта', () => {
    expect(coversNewAccount({ mode: 'all', ids: [] }, undefined, CREATED)).toBe(true);
    expect(coversNewAccount({ mode: 'all_real', ids: [] }, undefined, CREATED)).toBe(false);
    expect(coversNewAccount({ mode: 'all_real', ids: [] }, undefined, CREATED_REAL)).toBe(true);
  });
});

describe('хранилище выбора', () => {
  it('пресет «Все реальные» — правило без списка id', () => {
    useAccountSelectionStore.getState().selectIds([FIRST]);
    useAccountSelectionStore.getState().selectAllReal();

    expect(useAccountSelectionStore.getState()).toMatchObject({ mode: 'all_real', ids: [] });
  });

  /**
   * Основа щелчка — то, что нарисовано отмеченным, и приходит она снаружи: правило
   * `all_real` разворачивается в список счетов, которого store не видит.
   */
  it('галочка поверх пресета вычитает счёт из развёрнутого правила, а не начинает с нуля', () => {
    useAccountSelectionStore.getState().selectAllReal();
    // Экран нарисовал отмеченными оба реальных счёта — их и передаёт.
    useAccountSelectionStore.getState().toggleId(FIRST, [FIRST, SECOND]);

    expect(useAccountSelectionStore.getState()).toMatchObject({ mode: 'single', ids: [SECOND] });
  });

  it('галочка на счёте, которого в правиле не было, добавляет его к развёрнутому списку', () => {
    useAccountSelectionStore.getState().selectAllReal();
    useAccountSelectionStore.getState().toggleId(SECOND, [FIRST]);

    expect(useAccountSelectionStore.getState()).toMatchObject({
      mode: 'multi',
      ids: [FIRST, SECOND],
    });
  });

  it('снятая последняя галочка возвращает выбор к «всем»', () => {
    const { toggleId } = useAccountSelectionStore.getState();

    toggleId(FIRST, []);
    expect(useAccountSelectionStore.getState()).toMatchObject({ mode: 'single', ids: [FIRST] });

    toggleId(FIRST, [FIRST]);
    expect(useAccountSelectionStore.getState()).toMatchObject({ mode: 'all', ids: [] });
  });

  it('первая галочка поверх «всех» выбирает один счёт: отмеченного там нет ничего', () => {
    useAccountSelectionStore.getState().selectAll();
    // При пресете «Все» галочки сняты, поэтому основа щелчка пуста.
    useAccountSelectionStore.getState().toggleId(SECOND, []);

    expect(useAccountSelectionStore.getState().ids).toEqual([SECOND]);
  });

  it('выбор переживает перезагрузку', async () => {
    useAccountSelectionStore.getState().selectIds([FIRST, SECOND]);
    const stored = window.localStorage.getItem(SELECTION_STORAGE_KEY);

    expect(stored).toContain(FIRST);

    // Перезагрузка страницы — это чистая память при сохранившемся хранилище. Правка
    // состояния сама пишет в хранилище, поэтому записанное возвращается обратно.
    useAccountSelectionStore.setState({ mode: 'all', ids: [] });
    window.localStorage.setItem(SELECTION_STORAGE_KEY, stored as string);
    await useAccountSelectionStore.persist.rehydrate();

    expect(useAccountSelectionStore.getState()).toMatchObject({
      mode: 'multi',
      ids: [FIRST, SECOND],
    });
  });

  it('испорченное значение в хранилище не ломает приложение', async () => {
    window.localStorage.setItem(
      SELECTION_STORAGE_KEY,
      JSON.stringify({ state: { mode: 'что угодно', ids: [42, null, FIRST] }, version: 0 }),
    );

    await useAccountSelectionStore.persist.rehydrate();

    expect(useAccountSelectionStore.getState()).toMatchObject({ mode: 'single', ids: [FIRST] });
  });

  it('нечитаемое хранилище означает «все счета», а не пустой экран', async () => {
    window.localStorage.setItem(SELECTION_STORAGE_KEY, 'не json');

    await useAccountSelectionStore.persist.rehydrate();

    expect(useAccountSelectionStore.getState().mode).toBe('all');
  });
});
