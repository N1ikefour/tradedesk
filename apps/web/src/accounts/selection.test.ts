import { beforeEach, describe, expect, it } from 'vitest';

import type { Account } from '@/accounts/api';
import {
  SELECTION_STORAGE_KEY,
  resolveSelection,
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

describe('хранилище выбора', () => {
  it('снятая последняя галочка возвращает выбор к «всем»', () => {
    const { toggleId } = useAccountSelectionStore.getState();

    toggleId(FIRST);
    expect(useAccountSelectionStore.getState()).toMatchObject({ mode: 'single', ids: [FIRST] });

    toggleId(FIRST);
    expect(useAccountSelectionStore.getState()).toMatchObject({ mode: 'all', ids: [] });
  });

  it('первая галочка поверх «всех» выбирает один счёт, а не добавляет к невидимому списку', () => {
    useAccountSelectionStore.getState().selectAll();
    useAccountSelectionStore.getState().toggleId(SECOND);

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
