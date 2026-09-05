import { useCallback, useState } from 'react';

import { applyTheme, readStoredTheme, storeTheme, type Theme } from '@/lib/theme';

/**
 * Тему на первом кадре ставит скрипт в `index.html`, здесь — только переключение.
 * Начальное значение читается из того же хранилища, чтобы состояние React совпало
 * с уже нарисованным документом.
 */
export function useTheme(): { theme: Theme; toggleTheme: () => void } {
  const [theme, setTheme] = useState<Theme>(readStoredTheme);

  const toggleTheme = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      storeTheme(next);
      return next;
    });
  }, []);

  return { theme, toggleTheme };
}
