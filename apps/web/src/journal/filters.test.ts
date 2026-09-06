import { describe, expect, it } from 'vitest';

import {
  DEFAULT_FILTERS,
  isDefaultFilters,
  readFilters,
  toQueryParams,
  writeFilters,
  type JournalFilters,
} from '@/journal/filters';

const CONTEXT = {
  accountIds: [] as readonly string[],
  now: new Date('2026-09-06T05:00:00Z'),
  timeZone: 'Europe/Moscow',
  dayBoundaryHour: 7,
};

function read(search: string): JournalFilters {
  return readFilters(new URLSearchParams(search));
}

/** Ключи, которые эндпоинт вообще знает. Всё сверх них — `400` из-за `extra="forbid"`. */
const ALLOWED_QUERY_KEYS = new Set([
  'account_ids',
  'status',
  'from',
  'to',
  'symbol',
  'direction',
  'result',
  'tags',
  'has_reflection',
  'q',
  'sort',
  'limit',
  'cursor',
]);

describe('чтение фильтров из адреса', () => {
  it('пустой адрес — состояние по умолчанию', () => {
    expect(read('')).toEqual(DEFAULT_FILTERS);
    expect(isDefaultFilters(read(''))).toBe(true);
  });

  it('читает всё, что панель умеет ставить', () => {
    const filters = read(
      'period=week&status=open&symbol=eurusd&direction=short&result=loss' +
        '&tags=news,plan&reflection=none&q=пробой&sort=net_pnl:asc',
    );

    expect(filters).toEqual({
      period: 'week',
      from: null,
      to: null,
      status: 'open',
      symbol: 'eurusd',
      direction: 'short',
      result: 'loss',
      tags: ['news', 'plan'],
      reflection: 'none',
      q: 'пробой',
      sortField: 'net_pnl',
      sortDirection: 'asc',
    });
  });

  it('испорченные значения не применяются и не роняют разбор', () => {
    const filters = read(
      'period=позавчера&status=zzz&direction=diagonal&result=maybe' +
        '&reflection=1&sort=DROP TABLE&from=вчера&to=%%%&utm_source=письмо',
    );

    expect(filters).toEqual(DEFAULT_FILTERS);
  });

  it('слишком длинные значения подрезаются до пределов сервера', () => {
    const filters = read(`symbol=${'A'.repeat(50)}&q=${'б'.repeat(200)}`);

    expect(filters.symbol).toHaveLength(32);
    expect(filters.q).toHaveLength(100);
  });

  it('теги чистятся, повторы схлопываются, длинные и лишние отбрасываются', () => {
    const many = Array.from({ length: 30 }, (_, index) => `tag${index}`).join(',');

    expect(read('tags=,%20news%20,news,,plan').tags).toEqual(['news', 'plan']);
    expect(read(`tags=${many}`).tags).toHaveLength(20);
    expect(read(`tags=${'x'.repeat(65)},ok`).tags).toEqual(['ok']);
  });

  it('явные границы периода перебивают пресет', () => {
    const filters = read('period=week&from=2026-09-01T00:00:00Z&to=2026-09-02T00:00:00Z');

    expect(filters.period).toBe('custom');
    expect(filters.from).toBe('2026-09-01T00:00:00Z');
    expect(filters.to).toBe('2026-09-02T00:00:00Z');
  });

  it('управляющие символы не доезжают до сервера: NUL в тексте — это 500, а не фильтр', () => {
    const nul = String.fromCharCode(0);

    expect(read(`symbol=${encodeURIComponent(`${nul}${nul}EURUSD`)}`).symbol).toBe('EURUSD');
    expect(read(`q=${encodeURIComponent(`${nul}пробой`)}`).q).toBe('пробой');
    expect(read(`tags=${encodeURIComponent(`${nul}news`)},plan`).tags).toEqual(['news', 'plan']);
    // Значение, от которого после чистки ничего не осталось, — это отсутствие фильтра.
    expect(read(`symbol=${encodeURIComponent(nul)}`).symbol).toBe('');
    expect(read(`tags=${encodeURIComponent(nul)}`).tags).toEqual([]);
  });

  it('невидимки из копипасты не превращают EURUSD в другой символ', () => {
    // U+200B и U+FEFF приезжают вставкой из мессенджера и на экране не видны вовсе.
    expect(read('symbol=%E2%80%8BEURUSD%EF%BB%BF').symbol).toBe('EURUSD');
  });

  it('дата вне диапазона сервера не применяется: toISOString печатает расширенный год', () => {
    expect(read('from=99999-01-01').from).toBeNull();
    expect(read('from=%2B010000-01-01').from).toBeNull();
    expect(read('from=-000001-01-01').from).toBeNull();
    // Год, который сервер принимает, остаётся фильтром.
    expect(read('from=2026-09-01T00:00:00Z').from).toBe('2026-09-01T00:00:00Z');
  });

  it('перевёрнутый период не применяется: сервер отверг бы его целиком', () => {
    const filters = read('from=2026-09-05T00:00:00Z&to=2026-09-01T00:00:00Z');

    expect(filters.period).toBe('all');
    expect(filters.from).toBeNull();
    expect(filters.to).toBeNull();
  });
});

describe('запись фильтров в адрес', () => {
  it('значения по умолчанию в адрес не попадают', () => {
    expect(writeFilters(DEFAULT_FILTERS).toString()).toBe('');
  });

  it('адрес переживает круг «прочитать → записать → прочитать»', () => {
    const search =
      'period=month&status=closed&symbol=XAUUSD&direction=long&result=win' +
      '&tags=news%2Cplan&reflection=filled&q=gap&sort=duration_seconds:asc';
    const once = read(search);

    expect(readFilters(writeFilters(once))).toEqual(once);
  });

  it('чужие параметры из ссылки не переезжают в новый адрес', () => {
    const filters = read('symbol=EURUSD&utm_source=telegram&fbclid=1');

    expect(writeFilters(filters).toString()).toBe('symbol=EURUSD');
  });
});

describe('параметры запроса', () => {
  it('не содержит ключей, которых эндпоинт не знает', () => {
    const params = toQueryParams(read('symbol=EURUSD&result=win'), CONTEXT);

    for (const key of Object.keys(params)) {
      expect(ALLOWED_QUERY_KEYS).toContain(key);
    }
  });

  it('пресет разворачивается в границу торгового дня пользователя', () => {
    expect(toQueryParams(read('period=today'), CONTEXT).from).toBe('2026-09-06T04:00:00.000Z');
    expect(toQueryParams(read('period=all'), CONTEXT).from).toBeUndefined();
  });

  it('«не заполнена» уходит как has_reflection=false', () => {
    expect(toQueryParams(read('reflection=none'), CONTEXT).has_reflection).toBe(false);
    expect(toQueryParams(read('reflection=filled'), CONTEXT).has_reflection).toBe(true);
    expect(toQueryParams(read(''), CONTEXT).has_reflection).toBeUndefined();
  });

  it('счета уходят одним параметром через запятую, пустой выбор — не уходит вовсе', () => {
    const ids = ['0199a2b0-0000-7000-8000-0000000000a1', '0199a2b0-0000-7000-8000-0000000000a2'];

    expect(toQueryParams(read(''), { ...CONTEXT, accountIds: ids }).account_ids).toBe(
      ids.join(','),
    );
    expect(toQueryParams(read(''), CONTEXT).account_ids).toBeUndefined();
  });

  it('сортировка и размер страницы уходят всегда', () => {
    const params = toQueryParams(read(''), CONTEXT);

    expect(params.sort).toBe('close_time:desc');
    expect(params.limit).toBe(50);
  });

  it('свой период уходит как есть, приведённый к UTC', () => {
    const params = toQueryParams(read('from=2026-09-01T03:00:00%2B03:00'), CONTEXT);

    expect(params.from).toBe('2026-09-01T00:00:00.000Z');
  });
});
