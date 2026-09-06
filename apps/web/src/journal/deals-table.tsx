/**
 * Блок «Сделки брокера» — SPEC.md 9.3, только чтение. Это факты терминала: они
 * append-only и правке не подлежат в принципе (`CLAUDE.md` §2).
 *
 * Пустая таблица — штатное состояние, а не поломка: позиции сегодня собирать некому
 * (`S1-03`), а у ручной сделки (`S2-03`) deal будет один синтетический. Поэтому вместо
 * пустой рамки здесь написано, откуда строки берутся.
 */
import { Card, CardContent } from '@/components/ui/card';
import { t } from '@/i18n';
import type { Deal } from '@/journal/api';
import { dictionaryLabel, pnlToneClass } from '@/journal/position-view';
import { decimalSign, formatMoney, formatPrice, formatVolume } from '@/lib/decimal';
import { formatDateTime } from '@/lib/format';
import { cn } from '@/lib/utils';
import { useProfileTimeZone } from '@/user/profile';

function money(raw: string): string {
  return formatMoney(raw) ?? t.position.unknownValue;
}

export function DealsTable({ deals }: { deals: readonly Deal[] }) {
  const timeZone = useProfileTimeZone();

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-5">
        <div className="flex flex-col gap-1">
          <h2 className="text-sm font-medium">{t.position.dealsTitle}</h2>
          <p className="text-xs text-muted-foreground">{t.position.dealsHint}</p>
        </div>

        {deals.length === 0 ? (
          <div className="flex flex-col gap-1">
            <p className="text-sm">{t.position.dealsEmpty}</p>
            <p className="text-xs text-muted-foreground">{t.position.dealsEmptyHint}</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th scope="col" className="py-2 pr-4 font-medium">
                    {t.position.dealTime}
                  </th>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    {t.position.dealType}
                  </th>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    {t.position.dealEntry}
                  </th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">
                    {t.position.dealVolume}
                  </th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">
                    {t.position.dealPrice}
                  </th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">
                    {t.position.dealProfit}
                  </th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">
                    {t.position.dealCommission}
                  </th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">
                    {t.position.dealSwap}
                  </th>
                  <th scope="col" className="py-2 pr-4 font-medium">
                    {t.position.dealTicket}
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    {t.position.dealComment}
                  </th>
                </tr>
              </thead>
              <tbody>
                {deals.map((deal) => (
                  <tr key={deal.deal_ticket} className="border-t border-border">
                    <td className="py-2 pr-4 whitespace-nowrap">
                      {formatDateTime(deal.time_utc, timeZone)}
                    </td>
                    <td className="py-2 pr-4">
                      {dictionaryLabel(t.position.dealTypes, deal.deal_type)}
                    </td>
                    <td className="py-2 pr-4">
                      {dictionaryLabel(t.position.dealEntries, deal.entry)}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      {formatVolume(deal.volume) ?? t.position.unknownValue}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      {formatPrice(deal.price) ?? t.position.unknownValue}
                    </td>
                    <td
                      className={cn(
                        'py-2 pr-4 text-right tabular-nums',
                        pnlToneClass(decimalSign(deal.profit) ?? 'zero'),
                      )}
                    >
                      {money(deal.profit)}
                    </td>
                    <td className="py-2 pr-4 text-right tabular-nums">{money(deal.commission)}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{money(deal.swap)}</td>
                    <td className="py-2 pr-4 tabular-nums">{deal.deal_ticket}</td>
                    <td className="py-2 text-muted-foreground">
                      {/* Причина закрытия и комментарий брокера — единственное, что
                          объясняет строку: стоп это был, тейк или рука. */}
                      {[
                        deal.reason === null
                          ? null
                          : dictionaryLabel(t.position.dealReasons, deal.reason),
                        deal.comment,
                      ]
                        .filter((value): value is string => value !== null && value !== '')
                        .join(' · ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
