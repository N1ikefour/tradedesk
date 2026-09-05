import { Card, CardContent } from '@/components/ui/card';
import { t } from '@/i18n';

/**
 * Блок «Коллектор» из SPEC.md 9.3. Объясняет, почему добавленный счёт сам по себе ничего
 * не приносит: программа, которая ходит в терминал, стоит на машине пользователя, и до её
 * запуска экран останется пустым.
 *
 * Про `X-25` сказано прямо: пока `check_collectors` никто не зовёт по расписанию, счёт с
 * замолчавшим коллектором остаётся `connected`. Значит статусу верить нельзя, а времени
 * последней связи — можно, и человеку названо именно то, на что смотреть.
 */
export function CollectorBlock() {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 p-5">
        <h2 className="text-sm font-medium">{t.accounts.collectorTitle}</h2>
        <p className="text-sm text-muted-foreground">{t.accounts.collectorHint}</p>
        <p className="text-sm text-muted-foreground">{t.accounts.collectorSetup}</p>
        <p className="text-sm text-muted-foreground">{t.accounts.collectorStaleNote}</p>
        <p className="text-xs text-muted-foreground">{t.accounts.collectorNotReady}</p>
      </CardContent>
    </Card>
  );
}
