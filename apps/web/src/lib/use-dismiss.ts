/**
 * Закрытие всплывающего слоя по Escape и по клику мимо, с возвратом фокуса на кнопку.
 *
 * Выпадающие списки в шапке сделаны руками, без `@radix-ui/react-dropdown-menu`: всё их
 * поведение сводится к этим правилам, и ради него в проект не заводится ещё одна
 * зависимость. Правила выделены сюда, когда у переключателя счетов появился второй сосед
 * с тем же поведением — меню шапки на телефоне (X-36).
 */
import { useEffect, type RefObject } from 'react';

export function useDismiss(
  open: boolean,
  container: RefObject<HTMLElement | null>,
  trigger: RefObject<HTMLElement | null>,
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
      if (event.key !== 'Escape') {
        return;
      }
      // Закрытый слой уносит с собой фокус: пункт, на котором стоял человек, исчезает из
      // документа, и фокус достаётся `body` — следующий Tab уходит в начало страницы, а
      // не к соседу по шапке. На телефоне это меню — вся навигация (X-36), терять в нём
      // место нельзя. Возврат только если фокус был внутри слоя: Escape слушается на
      // документе, и нажать его могли, работая совсем в другом месте экрана.
      const restoreFocus = container.current?.contains(document.activeElement) ?? false;
      onDismiss();
      if (restoreFocus) {
        trigger.current?.focus();
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, container, trigger, onDismiss]);
}
