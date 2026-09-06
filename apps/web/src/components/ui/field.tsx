import type { ReactNode } from 'react';

import { Label } from '@/components/ui/label';

/** Атрибуты, которые поле обязано получить от обёртки: связь с подписью, подсказкой и ошибкой. */
export type FieldControlProps = {
  id: string;
  'aria-invalid': boolean;
  'aria-describedby': string | undefined;
};

/**
 * Подпись, подсказка и ошибка вокруг одного поля, связанные через `aria-describedby`.
 * Собрано в одном месте не ради экономии строк: скринридер объявляет подсказку только
 * при верной связке `id`, и копии этой связки расходятся первыми.
 */
export function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string | null;
  children: (props: FieldControlProps) => ReactNode;
}) {
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint === undefined ? null : hintId, error ? errorId : null]
    .filter((value): value is string => value !== null)
    .join(' ');

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      {children({
        id,
        'aria-invalid': Boolean(error),
        'aria-describedby': describedBy === '' ? undefined : describedBy,
      })}
      {hint === undefined ? null : (
        <div id={hintId} className="flex flex-col gap-2 text-xs text-muted-foreground">
          {hint}
        </div>
      )}
      {error ? (
        <p id={errorId} role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
