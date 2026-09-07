/**
 * Открытые позиции — SPEC.md 9.3.
 *
 * ⚠️ Спека обещает здесь «текущий `profit` из последнего `open_positions`». Взять его
 * негде: сборщик позиций плавающий результат не хранит (`docs/metrics.md` §7), а ингеста,
 * который приносит батчи коллектора, ещё нет (`S1-04`). Поэтому колонки с результатом
 * здесь нет вовсе, а её отсутствие объяснено на экране: пустая колонка читалась бы как
 * «не загрузилось», а поставленное туда `net_pnl` было бы накопленными издержками под
 * видом прибыли.
 */
import { Link } from 'react-router';

import { BlockStatus, DashboardBlock, type BlockQueryState } from '@/dashboard/block';
import { OPEN_POSITIONS_LIMIT } from '@/dashboard/api';
import { journalOpenLink } from '@/dashboard/period';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { t } from '@/i18n';
import type { PositionsPage } from '@/journal/api';
import { describePosition } from '@/journal/position-view';

export function OpenPositions({
  query,
  page,
  timeZone,
}: {
  query: BlockQueryState;
  page: PositionsPage | undefined;
  timeZone: string;
}) {
  const items = page?.items ?? [];
  const views = items.map((item) => describePosition(item, timeZone, ''));

  return (
    <DashboardBlock
      title={t.dashboard.openTitle}
      hint={t.dashboard.openHint}
      action={
        views.length === 0 ? null : (
          <Button type="button" variant="link" size="sm" className="h-auto p-0" asChild>
            <Link to={journalOpenLink()}>{t.dashboard.openAll}</Link>
          </Button>
        )
      }
    >
      <BlockStatus query={query} failedMessage={t.dashboard.openFailed} />
      {page === undefined ? null : views.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t.dashboard.openEmpty}</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr>
                  <th scope="col" className="px-2 py-1 text-left font-medium">
                    {t.dashboard.columnSymbol}
                  </th>
                  <th scope="col" className="px-2 py-1 text-left font-medium">
                    {t.dashboard.columnDirection}
                  </th>
                  <th scope="col" className="px-2 py-1 text-right font-medium">
                    {t.dashboard.columnVolume}
                  </th>
                  <th scope="col" className="px-2 py-1 text-right font-medium">
                    {t.dashboard.columnEntry}
                  </th>
                  <th scope="col" className="px-2 py-1 text-left font-medium">
                    {t.dashboard.columnOpenedAt}
                  </th>
                  <th scope="col" className="px-2 py-1 text-left font-medium">
                    {t.dashboard.columnAccount}
                  </th>
                </tr>
              </thead>
              <tbody>
                {views.map((view) => (
                  <tr key={view.id} className="border-t border-border">
                    <td className="px-2 py-1.5 font-medium">
                      <Link to={view.href} className="hover:underline">
                        {view.symbol}
                      </Link>
                    </td>
                    <td className="px-2 py-1.5">{view.directionLabel}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{view.volume}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{view.entryPrice}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap tabular-nums">{view.openTime}</td>
                    <td className="px-2 py-1.5">
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          aria-hidden="true"
                          className="size-2 shrink-0 rounded-full"
                          style={{ backgroundColor: view.accountColor }}
                        />
                        <span className="truncate">{view.accountTitle}</span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {page.next_cursor === null ? null : (
            <Badge tone="neutral">{t.dashboard.openMore(OPEN_POSITIONS_LIMIT)}</Badge>
          )}
          <p className="text-xs text-muted-foreground">{t.dashboard.openNoProfit}</p>
        </>
      )}
    </DashboardBlock>
  );
}
