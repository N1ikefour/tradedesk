import { useEffect, useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { t } from '@/i18n';
import { cn } from '@/lib/utils';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Модальное окно на своих руках, без `@radix-ui/react-dialog`: новая зависимость ради
 * одного экрана не нужна, а нативный `<dialog>` в jsdom не реализован — окно, которое
 * нельзя проверить тестом, здесь хуже полусотни строк своего кода.
 *
 * Что окно обязано уметь и умеет: объявляться как диалог, забирать фокус, держать Tab
 * внутри себя, закрываться по Escape и по клику мимо, возвращать фокус вызвавшей кнопке.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const panel = useRef<HTMLDivElement | null>(null);
  const restoreFocusTo = useRef<Element | null>(null);

  // Обработчик закрытия читается через ref, а эффект зависит только от `open`. Иначе
  // достаточно вызывающему передать стрелку — а он её и передаёт, — чтобы `onClose`
  // менялся каждый рендер: эффект переигрывался бы на каждое нажатие клавиши, возвращая
  // фокус на первую кнопку окна. Ввод в поле при этом теряется со второго символа.
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  });

  useEffect(() => {
    if (!open) {
      return;
    }
    restoreFocusTo.current = document.activeElement;
    const node = panel.current;
    node?.querySelector<HTMLElement>(FOCUSABLE)?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        closeRef.current();
        return;
      }
      if (event.key !== 'Tab' || node === null) {
        return;
      }
      const focusable = [...node.querySelectorAll<HTMLElement>(FOCUSABLE)];
      if (focusable.length === 0) {
        return;
      }
      const first = focusable[0] as HTMLElement;
      const last = focusable[focusable.length - 1] as HTMLElement;
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === node)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      // Фокус возвращается той кнопке, что открыла окно: иначе после закрытия он падает
      // на <body>, и клавиатура начинает обход страницы заново.
      if (restoreFocusTo.current instanceof HTMLElement) {
        restoreFocusTo.current.focus();
      }
    };
  }, [open]);

  if (!open) {
    return null;
  }

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 sm:items-center"
      // mousedown, а не click: клик, начатый внутри окна и отпущенный на подложке
      // (выделение текста мышью), иначе закрывал бы форму вместе с введённым.
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description === undefined ? undefined : descriptionId}
        className={cn(
          'relative my-8 w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-xl',
          className,
        )}
      >
        <div className="flex items-start gap-4">
          <h2 id={titleId} className="text-lg leading-tight font-semibold">
            {title}
          </h2>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="-mt-1 ml-auto shrink-0"
            aria-label={t.common.close}
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </Button>
        </div>
        {description === undefined ? null : (
          <div id={descriptionId} className="mt-2 text-sm text-muted-foreground">
            {description}
          </div>
        )}
        <div className="mt-4">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
