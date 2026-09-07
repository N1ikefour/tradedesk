/**
 * Числа берутся из `docs/metrics.md` §4 — того самого примера, который считается на
 * бумаге и на котором стоят серверные тесты формул. Экран обязан показывать ровно его:
 * если фронт округлит или переведёт долю по-своему, человек увидит не то число, которое
 * посчитал сервер.
 */
import { describe, expect, it } from 'vitest';

import type { Summary } from '@/dashboard/api';
import { describeSummary, type Metric } from '@/dashboard/summary-view';
import { t } from '@/i18n';

/** Разделитель разрядов и отбивка единицы — неразрывный пробел (SPEC.md 9.4). */
const NB = '\u00a0';

/** Пример `docs/metrics.md` §4: восемь закрытых позиций и две открытые. */
const PAPER_EXAMPLE: Summary = {
  trades: 8,
  wins: 4,
  losses: 3,
  breakeven: 1,
  open_positions: 2,
  winrate: '0.5000',
  net_pnl: '117.00',
  gross_pnl: '144.50',
  commission: '-22.00',
  swap: '-4.50',
  fee: '-1.00',
  profit_factor: '2.17',
  avg_win: '54.25',
  avg_loss: '-33.33',
  expectancy: '14.63',
  best_trade: '116.00',
  worst_trade: '-52.00',
};

const EMPTY: Summary = {
  trades: 0,
  wins: 0,
  losses: 0,
  breakeven: 0,
  open_positions: 0,
  winrate: null,
  net_pnl: '0.00',
  gross_pnl: '0.00',
  commission: '0.00',
  swap: '0.00',
  fee: '0.00',
  profit_factor: null,
  avg_win: null,
  avg_loss: null,
  expectancy: null,
  best_trade: null,
  worst_trade: null,
};

function metric(view: ReturnType<typeof describeSummary>, key: string): Metric {
  const found = [...view.headline, ...view.details].find((item) => item.key === key);
  if (found === undefined) {
    throw new Error(`нет метрики ${key}`);
  }
  return found;
}

describe('сводка на экране', () => {
  it('печатает числа примера из docs/metrics.md §4', () => {
    const view = describeSummary(PAPER_EXAMPLE);

    expect(view.netPnl.value).toBe(`117,00${NB}$`);
    expect(view.netPnl.sign).toBe('positive');
    expect(metric(view, 'trades').value).toBe('8');
    // Доля 0…1 приходит с сервера, проценты — работа фронта (docs/metrics.md §3.2).
    // Знаков два: доля посчитана с четырьмя, и один из них экран терять не должен.
    expect(metric(view, 'winrate').value).toBe(`50,00${NB}%`);
    expect(metric(view, 'profit_factor').value).toBe('2,17');
    expect(metric(view, 'avg_win').value).toBe(`54,25${NB}$`);
    // Средний убыток отрицателен — это деньги, а не модуль.
    expect(metric(view, 'avg_loss').value).toBe(`-33,33${NB}$`);
    expect(metric(view, 'avg_loss').sign).toBe('negative');
    expect(metric(view, 'expectancy').value).toBe(`14,63${NB}$`);
    expect(metric(view, 'best_trade').value).toBe(`116,00${NB}$`);
    expect(metric(view, 'worst_trade').value).toBe(`-52,00${NB}$`);
    expect(metric(view, 'gross_pnl').value).toBe(`144,50${NB}$`);
    expect(metric(view, 'commission').value).toBe(`-22,00${NB}$`);
    expect(metric(view, 'fee').value).toBe(`-1,00${NB}$`);
  });

  it('сходится арифметика, которую человек проверяет глазами', () => {
    const view = describeSummary(PAPER_EXAMPLE);
    const counts = ['wins', 'losses', 'breakeven'].map((key) => Number(metric(view, key).value));

    expect(counts.reduce((sum, value) => sum + value, 0)).toBe(PAPER_EXAMPLE.trades);
  });

  it('пусто — это «нечего считать», и подпись говорит, чего именно не было', () => {
    const view = describeSummary(EMPTY);

    expect(metric(view, 'winrate').value).toBe(t.dashboard.unknownValue);
    expect(metric(view, 'winrate').note).toBe(t.dashboard.noteNoTrades);
    expect(metric(view, 'profit_factor').note).toBe(t.dashboard.noteNoTrades);
    // Денежные суммы пустого множества — честный ноль, а не прочерк.
    expect(view.netPnl.value).toBe(`0,00${NB}$`);
  });

  it('профит-фактор без убытков — прочерк с причиной, а не ноль', () => {
    const view = describeSummary({
      ...PAPER_EXAMPLE,
      losses: 0,
      wins: 5,
      breakeven: 3,
      profit_factor: null,
      avg_loss: null,
    });

    expect(metric(view, 'profit_factor').value).toBe(t.dashboard.unknownValue);
    expect(metric(view, 'profit_factor').note).toBe(t.dashboard.noteNoLosses);
    expect(metric(view, 'avg_loss').note).toBe(t.dashboard.noteNoLosses);
  });

  it('нулевой профит-фактор — посчитанный ноль, а не прочерк', () => {
    // Третья строка таблицы docs/metrics.md §3.1: есть убытки и нет прибыли. Это
    // единственный случай, когда «0.00» у профит-фактора — факт, а не отсутствие числа.
    const view = describeSummary({
      ...PAPER_EXAMPLE,
      wins: 0,
      losses: 7,
      breakeven: 1,
      winrate: '0.0000',
      profit_factor: '0.00',
      avg_win: null,
    });

    expect(metric(view, 'profit_factor').value).toBe('0,00');
    expect(metric(view, 'profit_factor').note).toBeNull();
    expect(metric(view, 'winrate').value).toBe(`0,00${NB}%`);
  });

  it('без выигрышных сказано именно это, а не «нет сделок»', () => {
    const view = describeSummary({ ...PAPER_EXAMPLE, wins: 0, avg_win: null });

    expect(metric(view, 'avg_win').note).toBe(t.dashboard.noteNoWins);
  });
});
