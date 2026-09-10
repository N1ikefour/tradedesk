import { Card, CardContent } from '@/components/ui/card';
import { t } from '@/i18n';

/**
 * Блок «Коллектор» из SPEC.md 9.3. Объясняет, почему добавленный счёт сам по себе ничего
 * не приносит: программа, которая ходит в терминал, стоит на машине пользователя, и до её
 * запуска экран останется пустым.
 *
 * С `T-07` (ADR-0006) здесь же названо второе условие и его цена: коллектор подключается к
 * терминалу, который открыл человек, и синхронизируется тот счёт, под которым он вошёл.
 * Место выбрано осознанно — правило одно на все счета, а на карточке счёта стоит следствие
 * для него одного (`statusPendingHint`).
 *
 * Статусу счёта здесь верят: с `X-25` `check_collectors` ходит по расписанию и уводит
 * замолчавший `connected` в `needs_attention` сам. Порога «сколько молчать» в этих
 * текстах нет — он живёт на сервере (SPEC.md 9.3, решение `S1-11`).
 */
export function CollectorBlock() {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 p-5">
        <h2 className="text-sm font-medium">{t.accounts.collectorTitle}</h2>
        <p className="text-sm text-muted-foreground">{t.accounts.collectorHint}</p>
        <p className="text-sm text-foreground">{t.accounts.collectorOpenTerminal}</p>
        <p className="text-sm text-muted-foreground">{t.accounts.collectorOneAtATime}</p>
        <p className="text-sm text-muted-foreground">{t.accounts.collectorSetup}</p>
        <p className="text-sm text-muted-foreground">{t.accounts.collectorStaleNote}</p>
        <p className="text-xs text-muted-foreground">{t.accounts.collectorNotReady}</p>
      </CardContent>
    </Card>
  );
}
