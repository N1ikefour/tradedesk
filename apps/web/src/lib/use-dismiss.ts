/**
 * Закрытие всплывающего слоя по Escape и по клику мимо.
 *
 * Выпадающие списки в шапке сделаны руками, без `@radix-ui/react-dropdown-menu`: всё их
 * поведение сводится к этим двум правилам, и ради него в проект не заводится ещё одна
 * зависимость. Правила выделены сюда, когда у переключателя счетов появился второй сосед
 * с тем же поведением — меню шапки на телефоне (X-36).
 */
import { useEffect, type RefObject } from 'react';

export function useDismiss(
  open: boolean,
  container: RefObject<HTMLElement | null>,
  onDismiss: () => void,
): void {
  useEffect(() => {
    if (!open) {
      return;
    }
    const onPointerDown = (event: MouseEvent) => {
      if (container.current !== null && !container.current.contains(event.target as Node)) {
        onDismiss();
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onDismiss();
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, container, onDismiss]);
}
