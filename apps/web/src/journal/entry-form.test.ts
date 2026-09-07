import { describe, expect, it } from 'vitest';

import type { JournalEntryDetail } from '@/journal/api';
import {
  addTag,
  EMPTY_ENTRY_FORM,
  entryBody,
  entryErrors,
  entryFormFrom,
  MAX_TAGS,
  type EntryForm,
} from '@/journal/entry-form';

function detail(overrides: Partial<JournalEntryDetail> = {}): JournalEntryDetail {
  return {
    notes: null,
    tags: [],
    planned_entry: null,
    planned_sl: null,
    planned_tp: null,
    risk_amount: null,
    updated_at: '2026-09-05T10:00:00Z',
    ...overrides,
  };
}

function form(overrides: Partial<EntryForm> = {}): EntryForm {
  return { ...EMPTY_ENTRY_FORM, ...overrides };
}

describe('тело PUT /entry', () => {
  it('несёт все поля контракта, даже когда форма пуста', () => {
    // Ключи перечислены здесь целиком не для красоты: частичное тело — это «сотри
    // остальное» (SPEC.md 5.4), и пропажу поля должен ловить тест, а не пользователь.
    expect(Object.keys(entryBody(EMPTY_ENTRY_FORM) ?? {}).sort()).toEqual([
      'notes',
      'planned_entry',
      'planned_sl',
      'planned_tp',
      'risk_amount',
      'tags',
    ]);
  });

  it('очистка поля выражается явным null, а не пропуском', () => {
    expect(entryBody(EMPTY_ENTRY_FORM)).toEqual({
      notes: null,
      tags: [],
      planned_entry: null,
      planned_sl: null,
      planned_tp: null,
      risk_amount: null,
    });
  });

  it('деньги и цены уходят строками и никогда не числами', () => {
    const body = entryBody(
      form({ plannedEntry: '1,10500', plannedSl: '1.09000', riskAmount: '100' }),
    );
    expect(body?.planned_entry).toBe('1.105');
    expect(body?.planned_sl).toBe('1.09');
    expect(body?.risk_amount).toBe('100');
    for (const value of [body?.planned_entry, body?.planned_sl, body?.risk_amount]) {
      expect(typeof value).toBe('string');
    }
  });

  it('точность 18 знаков переживает дорогу через форму', () => {
    // Число выбрано так, что double его НЕ держит: то же значение стоит в decimal.test.ts.
    // С `12345678.12345678` этот тест был декорацией — оно проходит через double без
    // потерь, и подмена canonicalDecimal на `String(Number(...))` оставалась зелёной.
    const raw = '123456789012.12345678';
    expect(String(Number(raw))).not.toBe(raw);

    const body = entryBody(entryFormFrom(detail({ planned_entry: raw })));
    expect(body?.planned_entry).toBe(raw);
  });

  it('значение сервера и то же число, набранное руками, дают одно тело', () => {
    // Иначе форма считалась бы изменённой вечно, а автосохранение слало бы PUT по кругу.
    const fromServer = entryBody(entryFormFrom(detail({ planned_entry: '1.10000000' })));
    const typed = entryBody(form({ plannedEntry: '1,1' }));
    expect(typed).toEqual(fromServer);
  });

  it('не собирается, пока в поле не число', () => {
    expect(entryBody(form({ plannedSl: 'около 1.1' }))).toBeNull();
    expect(entryErrors(form({ plannedSl: 'около 1.1' })).plannedSl).toBe('number');
  });

  it('риск строго положителен: ноль перевернул бы R или поделил на ноль', () => {
    expect(entryErrors(form({ riskAmount: '0' })).riskAmount).toBe('positive');
    expect(entryErrors(form({ riskAmount: '-5' })).riskAmount).toBe('positive');
    expect(entryErrors(form({ riskAmount: '' })).riskAmount).toBeUndefined();
  });

  it('заметка из пробелов — это отсутствие заметки, как и на сервере', () => {
    expect(entryBody(form({ notes: '   ' }))?.notes).toBeNull();
    expect(entryBody(form({ notes: '  есть текст ' }))?.notes).toBe('есть текст');
  });
});

describe('теги позиции', () => {
  it('повтор без учёта регистра — тот же тег', () => {
    const result = addTag(['Trend'], 'trend');
    expect(result.rejected).toBe('duplicate');
    expect(result.tags).toEqual(['Trend']);
  });

  it('запятая запрещена: по ней разделяется фильтр журнала', () => {
    expect(addTag([], 'news, fomo').rejected).toBe('comma');
  });

  it('больше двадцати тегов на позицию не ставится', () => {
    const full = Array.from({ length: MAX_TAGS }, (_, index) => `tag${index}`);
    expect(addTag(full, 'ещё один').rejected).toBe('limit');
  });

  it('пробелы по краям срезаются, порядок ввода сохраняется', () => {
    expect(addTag(['a'], '  b  ').tags).toEqual(['a', 'b']);
  });
});
