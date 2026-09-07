/**
 * Ответ `GET /analytics/summary` → то, что видно на экране (SPEC.md 5.5, формулы
 * `docs/metrics.md` §3). Ни одно число здесь не считается заново — только оформляется.
 *
 * Главное решение модуля — что показывать вместо `null`. В контракте `null` означает
 * «нечего считать», а не «вышло ноль» (`docs/metrics.md` §3.1): профит-фактор без единой
 * убыточной сделки — лучший возможный результат, и ноль на его месте прочитался бы как
 * провал. Поэтому у прочерка всегда есть подпись, которая говорит, чего именно не было.
 */
import type { Summary } from '@/dashboard/api';
import { t } from '@/i18n';
import {
  decimalSign,
  formatMoney,
  formatPercent,
  formatRatio,
  type DecimalSign,
} from '@/lib/decimal';

export type Metric = {
  readonly key: string;
  readonly label: string;
  readonly value: string;
  /** Чего не было, если вместо числа прочерк. У посчитанного значения — `null`. */
  readonly note: string | null;
  /** Знак денежной величины: им красится число (SPEC.md 9.4). */
  readonly sign: DecimalSign | null;
};

export type SummaryView = {
  /** Итог периода — единственное число, которое человек сверяет с журналом. */
  readonly netPnl: Metric;
  readonly headline: readonly Metric[];
  readonly details: readonly Metric[];
};

function dash(key: string, label: string, note: string): Metric {
  return { key, label, value: t.dashboard.unknownValue, note, sign: null };
}

function money(key: string, label: string, raw: string): Metric {
  return {
    key,
    label,
    value: formatMoney(raw) ?? t.dashboard.unknownValue,
    note: null,
    sign: decimalSign(raw),
  };
}

function count(key: string, label: string, value: number): Metric {
  return { key, label, value: String(value), note: null, sign: null };
}

function optionalMoney(key: string, label: string, raw: string | null, note: string): Metric {
  return raw === null ? dash(key, label, note) : money(key, label, raw);
}

/**
 * Почему величина пуста. Различить случаи можно уже существующими полями ответа
 * (`docs/metrics.md` §3.1), отдельного признака в контракте нет и не нужно.
 */
function emptyReason(summary: Summary, kind: 'trades' | 'wins' | 'losses'): string {
  if (summary.trades === 0) {
    return t.dashboard.noteNoTrades;
  }
  return kind === 'wins' ? t.dashboard.noteNoWins : t.dashboard.noteNoLosses;
}

export function describeSummary(summary: Summary): SummaryView {
  const noTrades = t.dashboard.noteNoTrades;
  return {
    netPnl: money('net_pnl', t.dashboard.metricNetPnl, summary.net_pnl),
    headline: [
      count('trades', t.dashboard.metricTrades, summary.trades),
      summary.winrate === null
        ? dash('winrate', t.dashboard.metricWinrate, noTrades)
        : {
            key: 'winrate',
            label: t.dashboard.metricWinrate,
            value: formatPercent(summary.winrate) ?? t.dashboard.unknownValue,
            note: null,
            sign: null,
          },
      summary.profit_factor === null
        ? dash('profit_factor', t.dashboard.metricProfitFactor, emptyReason(summary, 'losses'))
        : {
            key: 'profit_factor',
            label: t.dashboard.metricProfitFactor,
            value: formatRatio(summary.profit_factor) ?? t.dashboard.unknownValue,
            note: null,
            sign: null,
          },
    ],
    details: [
      count('wins', t.dashboard.metricWins, summary.wins),
      count('losses', t.dashboard.metricLosses, summary.losses),
      count('breakeven', t.dashboard.metricBreakeven, summary.breakeven),
      optionalMoney(
        'avg_win',
        t.dashboard.metricAvgWin,
        summary.avg_win,
        emptyReason(summary, 'wins'),
      ),
      optionalMoney(
        'avg_loss',
        t.dashboard.metricAvgLoss,
        summary.avg_loss,
        emptyReason(summary, 'losses'),
      ),
      optionalMoney('expectancy', t.dashboard.metricExpectancy, summary.expectancy, noTrades),
      optionalMoney('best_trade', t.dashboard.metricBestTrade, summary.best_trade, noTrades),
      optionalMoney('worst_trade', t.dashboard.metricWorstTrade, summary.worst_trade, noTrades),
      money('gross_pnl', t.dashboard.metricGrossPnl, summary.gross_pnl),
      money('commission', t.dashboard.metricCommission, summary.commission),
      money('swap', t.dashboard.metricSwap, summary.swap),
      money('fee', t.dashboard.metricFee, summary.fee),
    ],
  };
}
