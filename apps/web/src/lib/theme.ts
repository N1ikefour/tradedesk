/**
 * Тема. По умолчанию тёмная (SPEC.md 12, 14), светлая — выбором пользователя.
 *
 * Первый кадр красит не этот модуль, а встроенный скрипт в `index.html`: он выполняется
 * до разбора остального документа, поэтому светлой вспышки нет. Здесь — то же правило
 * для переключения во время работы, и обе половины обязаны читать один ключ.
 */
export const THEME_STORAGE_KEY = 'td.theme.v1';

export type Theme = 'dark' | 'light';

export const DEFAULT_THEME: Theme = 'dark';

function isTheme(value: string | null): value is Theme {
  return value === 'dark' || value === 'light';
}

/** localStorage недоступен в приватных режимах и в jsdom без окна — это не ошибка. */
export function readStoredTheme(): Theme {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(stored) ? stored : DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.classList.toggle('dark', theme === 'dark');
  root.style.colorScheme = theme;
}

export function storeTheme(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Выбор не переживёт перезагрузку — приложению это не мешает.
  }
}
