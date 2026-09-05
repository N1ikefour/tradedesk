import { describe, expect, it } from 'vitest';

import {
  browserTimeZone,
  buildTimeZoneOptions,
  filterTimeZoneOptions,
  groupTimeZoneOptions,
  isKnownTimeZone,
  offsetLabel,
  withSelectedTimeZone,
} from '@/lib/time-zones';

// Зимняя дата: у половины списка летом другое смещение, и «сейчас» сделало бы
// ожидания теста зависимыми от дня прогона.
const WINTER = new Date('2026-01-15T12:00:00Z');

/**
 * Игрушечный ответ `GET /users/timezones`. Намеренно не пересекается с тем, что знает
 * движок «сверх» него: тест обязан ловить любое имя, добавленное мимо сервера.
 */
const SERVER_LIST = ['Europe/Moscow', 'Asia/Tokyo', 'Asia/Kolkata', 'Europe/Berlin'] as const;

function names(options: readonly { name: string }[]): string[] {
  return options.map((option) => option.name);
}

describe('offsetLabel', () => {
  it('целые часы, получасовые и 45-минутные зоны', () => {
    expect(offsetLabel('Europe/Moscow', WINTER)).toBe('UTC+3');
    expect(offsetLabel('UTC', WINTER)).toBe('UTC+0');
    expect(offsetLabel('America/New_York', WINTER)).toBe('UTC-5');
    expect(offsetLabel('Asia/Kolkata', WINTER)).toBe('UTC+5:30');
    expect(offsetLabel('Asia/Kathmandu', WINTER)).toBe('UTC+5:45');
  });

  it('незнакомая зона не роняет подпись', () => {
    expect(offsetLabel('Mars/Olympus', WINTER)).toBe('');
  });
});

describe('isKnownTimeZone', () => {
  it('отличает имя IANA от выдумки', () => {
    expect(isKnownTimeZone('Europe/Moscow')).toBe(true);
    expect(isKnownTimeZone('Mars/Olympus')).toBe(false);
    expect(isKnownTimeZone('')).toBe(false);
  });

  it('зона браузера всегда известна', () => {
    expect(isKnownTimeZone(browserTimeZone())).toBe(true);
  });
});

describe('buildTimeZoneOptions', () => {
  it('подпись — имя IANA и смещение: по одному имени зону не выбрать', () => {
    const options = buildTimeZoneOptions(SERVER_LIST, WINTER);
    const moscow = options.find((option) => option.name === 'Europe/Moscow');

    expect(moscow?.label).toBe('Europe/Moscow (UTC+3)');
    expect(moscow?.region).toBe('Europe');
  });

  it('в списке ровно переданные имена: движок не источник', () => {
    // Ровно тот дефект, ради которого маршрут и появился: `Intl.supportedValuesOf`
    // знает `Asia/Calcutta` и `America/New_York`, а сервер прислал не их. Ни одно
    // лишнее имя в меню попасть не должно — сервер его отвергнет `400`.
    const list = names(buildTimeZoneOptions(SERVER_LIST, WINTER));

    expect(list).toEqual([...SERVER_LIST].sort((a, b) => a.localeCompare(b, 'en')));
    expect(list).not.toContain('America/New_York');
    expect(list).not.toContain('Asia/Calcutta');
    expect(isKnownTimeZone('America/New_York')).toBe(true);
  });

  it('пустой список даёт пустое меню, а не подстановку своих имён', () => {
    expect(buildTimeZoneOptions([], WINTER)).toEqual([]);
  });

  it('список отсортирован и без повторов', () => {
    const list = names(buildTimeZoneOptions(['Europe/Moscow', ...SERVER_LIST], WINTER));

    expect(new Set(list).size).toBe(list.length);
    expect([...list].sort((a, b) => a.localeCompare(b, 'en'))).toEqual(list);
  });

  it('сохранённое значение остаётся выбираемым, даже если сервер его не прислал', () => {
    // Псевдонимы у браузера и у сервера расходятся: сохранённое значение может
    // отсутствовать и в ответе сервера, и у движка. Подменять его нельзя.
    const options = buildTimeZoneOptions(SERVER_LIST, WINTER, 'Europe/Kyiv');
    expect(names(options)).toContain('Europe/Kyiv');

    const unknown = buildTimeZoneOptions(SERVER_LIST, WINTER, 'Mars/Olympus');
    expect(unknown.find((option) => option.name === 'Mars/Olympus')?.label).toBe('Mars/Olympus');
  });
});

describe('filterTimeZoneOptions', () => {
  const options = buildTimeZoneOptions([...SERVER_LIST, 'America/New_York'], WINTER);

  it('пустой запрос ничего не отсекает', () => {
    expect(filterTimeZoneOptions(options, '  ')).toBe(options);
  });

  it('пробел ищет так же, как подчёркивание в имени', () => {
    expect(names(filterTimeZoneOptions(options, 'new york'))).toContain('America/New_York');
  });

  it('регистр не важен, а несуществующее не находится', () => {
    expect(names(filterTimeZoneOptions(options, 'MOSCOW'))).toEqual(['Europe/Moscow']);
    expect(filterTimeZoneOptions(options, 'нетзоны')).toHaveLength(0);
  });
});

describe('withSelectedTimeZone', () => {
  const options = buildTimeZoneOptions(SERVER_LIST, WINTER);

  it('возвращает выбранное в список, когда поиск его отсёк', () => {
    const visible = filterTimeZoneOptions(options, 'moscow');
    const result = withSelectedTimeZone(visible, options, 'Asia/Tokyo');

    expect(names(result)).toEqual(['Asia/Tokyo', 'Europe/Moscow']);
  });

  it('не дублирует выбранное, если оно уже видно', () => {
    const visible = filterTimeZoneOptions(options, 'moscow');
    expect(withSelectedTimeZone(visible, options, 'Europe/Moscow')).toBe(visible);
  });
});

describe('groupTimeZoneOptions', () => {
  it('делит по первому сегменту имени и сохраняет порядок', () => {
    // `UTC` — единственное имя без региона: группа «имя без региона» проверяется на нём.
    const options = buildTimeZoneOptions([...SERVER_LIST, 'UTC'], WINTER).filter(
      (option) => option.name !== 'Asia/Kolkata',
    );
    const groups = groupTimeZoneOptions(options);

    expect(groups.map((group) => group.region)).toEqual(['Asia', 'Europe', 'UTC']);
    expect(names(groups[1]?.options ?? [])).toEqual(['Europe/Berlin', 'Europe/Moscow']);
  });
});
