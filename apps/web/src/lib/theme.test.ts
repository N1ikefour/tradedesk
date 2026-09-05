import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { beforeEach, describe, expect, it } from 'vitest';

import {
  applyTheme,
  DEFAULT_THEME,
  readStoredTheme,
  storeTheme,
  THEME_STORAGE_KEY,
} from '@/lib/theme';

const indexHtml = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8');

describe('тема', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.className = '';
  });

  it('по умолчанию тёмная', () => {
    expect(DEFAULT_THEME).toBe('dark');
    expect(readStoredTheme()).toBe('dark');
  });

  it('первый кадр тёмный: класс стоит в самой разметке, а не ставится скриптом', () => {
    expect(indexHtml).toMatch(/<html[^>]*\sclass="dark"/);
  });

  it('ключ хранения один и тот же в разметке и в коде', () => {
    // Разойдутся — выбор светлой темы перестанет переживать перезагрузку,
    // и на первом кадре снова появится вспышка.
    expect(indexHtml).toContain(THEME_STORAGE_KEY);
  });

  it('выбор светлой темы сохраняется и применяется', () => {
    storeTheme('light');
    applyTheme('light');

    expect(readStoredTheme()).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('мусор в хранилище не ломает тему', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'neon');
    expect(readStoredTheme()).toBe('dark');
  });
});
