/**
 * Раскладка, о которой знает не только CSS. Обычно ширину решает Tailwind, но
 * виртуализация списка (`use-virtual-rows`) считает высоту строки числом — а у таблицы и
 * у мобильной карточки она разная. Значит выбор раскладки должен быть известен коду, а не
 * только стилям.
 */
import { useCallback, useMemo, useSyncExternalStore } from 'react';

/** Граница мобильной раскладки журнала — SPEC.md 9.3 (< 768px). */
export const DESKTOP_QUERY = '(min-width: 768px)';

function subscribeTo(query: string) {
  return (onChange: () => void): (() => void) => {
    // `matchMedia` нет в jsdom, а компонент обязан отрисоваться и там: без него экран
    // считается настольным, потому что тесты и сборка идут без окна браузера.
    const list = window.matchMedia?.(query);
    if (list === undefined) {
      return () => {};
    }
    list.addEventListener('change', onChange);
    return () => list.removeEventListener('change', onChange);
  };
}

export function useMediaQuery(query: string, fallback: boolean): boolean {
  const subscribe = useMemo(() => subscribeTo(query), [query]);
  const getSnapshot = useCallback(
    () => window.matchMedia?.(query).matches ?? fallback,
    [query, fallback],
  );
  return useSyncExternalStore(subscribe, getSnapshot, () => fallback);
}

/** `true` — настольная раскладка (таблица), `false` — мобильная (карточки). */
export function useIsDesktop(): boolean {
  return useMediaQuery(DESKTOP_QUERY, true);
}
