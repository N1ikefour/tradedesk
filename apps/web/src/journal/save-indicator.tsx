/**
 * Состояние автосохранения одним местом на все блоки карточки. Индикатор говорит о
 * записи на сервере, а не о содержимом поля: «сохранено» появляется только после ответа.
 */
import { Check, CircleAlert, Loader2, Pencil } from 'lucide-react';

import { messageForError } from '@/api/error-message';
import { Button } from '@/components/ui/button';
import { t } from '@/i18n';
import type { Autosave } from '@/journal/use-autosave';
import { cn } from '@/lib/utils';

export function SaveIndicator({
  autosave,
  announce = false,
  className,
}: {
  autosave: Autosave;
  /**
   * Объявлять изменения скринридеру. Запись журнала показывает индикатор в двух блоках —
   * «План» и «Заметки и теги» живут в одной записи, — и озвучивать их оба означало бы
   * повторять одно и то же дважды.
   */
  announce?: boolean;
  className?: string;
}) {
  const failed = autosave.state === 'failed';
  return (
    <div
      className={cn('flex flex-wrap items-center gap-2 text-xs', className)}
      aria-live={announce ? 'polite' : undefined}
    >
      <span
        className={cn(
          'inline-flex items-center gap-1.5',
          failed ? 'text-destructive' : 'text-muted-foreground',
        )}
      >
        {autosave.state === 'saving' ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
        ) : null}
        {autosave.state === 'saved' ? <Check className="size-3.5" aria-hidden="true" /> : null}
        {autosave.state === 'scheduled' ? <Pencil className="size-3.5" aria-hidden="true" /> : null}
        {failed || autosave.state === 'invalid' ? (
          <CircleAlert className="size-3.5" aria-hidden="true" />
        ) : null}
        {label(autosave.state)}
      </span>
      {failed ? (
        <>
          <span className="text-destructive">{messageForError(autosave.error)}</span>
          <Button type="button" variant="outline" size="sm" onClick={autosave.retry}>
            {t.position.saveRetry}
          </Button>
          <span className="text-muted-foreground">{t.position.saveFailedHint}</span>
        </>
      ) : null}
    </div>
  );
}

function label(state: Autosave['state']): string {
  switch (state) {
    case 'clean':
      return t.position.saveIdle;
    case 'scheduled':
      return t.position.saveScheduled;
    case 'saving':
      return t.position.saving;
    case 'saved':
      return t.position.saved;
    case 'failed':
      return t.position.saveFailed;
    case 'invalid':
      return t.position.saveBlocked;
  }
}
