/**
 * Сводка за 30 дней — SPEC.md 9.3.
 *
 * Главное здесь не числа, а строка под ними. Сводка считает **только закрытые** сделки
 * (SPEC.md 5.5), поэтому при открытых позициях её «Итог» не равен сумме колонки «Итог» в
 * журнале за тот же период — разница ровно на них. Расхождение появляется при первой же
 * открытой сделке, а не при ошибке, и человек с калькулятором приходит с багом, которого
 * нет. Поэтому число открытых названо, разница объяснена, а рядом стоит ссылка на журнал
 * с фильтром «Закрытые» — он сходится со сводкой до копейки.
 */
import { Link } from 'react-router';

import { BlockStatus, DashboardBlock, type BlockQueryState } from '@/dashboard/block';
import type { Summary } from '@/dashboard/api';
import { journalClosedLink } from '@/dashboard/period';
import { describeSummary, type Metric } from '@/dashboard/summary-view';
import { Button } from '@/components/ui/button';
import { t } from '@/i18n';
import { pnlToneClass } from '@/journal/position-view';
import { formatDateTime } from '@/lib/format';
import { cn } from '@/lib/utils';

function MetricTile({ metric, className }: { metric: Metric; className?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{metric.label}</span>
      <span
        className={cn(
          'font-medium tabular-nums',
          className,
          metric.sign === null ? undefined : pnlToneClass(metric.sign),
        )}
      >
        {metric.value}
      </span>
      {metric.note === null ? null : (
        <span className="text-[11px] text-muted-foreground">{metric.note}</span>
      )}
    </div>
  );
}

export function SummaryBlock({
  query,
  summary,
  periodFrom,
  timeZone,
}: {
  query: BlockQueryState;
  summary: Summary | undefined;
  periodFrom: string;
  timeZone: string;
}) {
  const status = <BlockStatus query={query} failedMessage={t.dashboard.summaryFailed} />;
  const view = summary === undefined ? null : describeSummary(summary);

  return (
    <DashboardBlock
      title={t.dashboard.summaryTitle}
      hint={t.dashboard.summaryPeriod(formatDateTime(periodFrom, timeZone))}
    >
      {status}
      {summary === undefined || view === null ? null : (
        <>
          {summary.trades === 0 ? (
            <p className="text-sm text-muted-foreground">{t.dashboard.summaryEmpty}</p>
          ) : (
            <>
              <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
                <MetricTile metric={view.netPnl} className="text-2xl" />
                {view.headline.map((metric) => (
                  <MetricTile key={metric.key} metric={metric} className="text-lg" />
                ))}
              </div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-3 border-t border-border pt-3 sm:grid-cols-4 lg:grid-cols-6">
                {view.details.map((metric) => (
                  <MetricTile key={metric.key} metric={metric} className="text-sm" />
                ))}
              </div>
            </>
          )}

          {summary.open_positions > 0 ? (
            <div className="flex flex-col items-start gap-2 rounded-md border border-border bg-muted/40 p-3">
              <p className="text-sm font-medium">
                {t.dashboard.openInPeriod(summary.open_positions)}
              </p>
              <p className="text-xs text-muted-foreground">{t.dashboard.openInPeriodHint}</p>
              <Button type="button" variant="outline" size="sm" asChild>
                <Link to={journalClosedLink()}>{t.dashboard.openInPeriodLink}</Link>
              </Button>
            </div>
          ) : summary.trades > 0 ? (
            <p className="text-xs text-muted-foreground">{t.dashboard.noOpenInPeriod}</p>
          ) : null}
        </>
      )}
    </DashboardBlock>
  );
}
