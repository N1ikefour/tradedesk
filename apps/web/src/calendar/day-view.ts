/**
 * Показ одного дня календаря: сумма, её знак, разбивка по счетам и подпись для чтения
 * с экрана. Ни одно число здесь не считается — только оформляется.
 *
 * Модуль общий у экрана `/calendar` и у календаря-мини дашборда: две копии этого
 * оформления разошлись бы в цвете и в округлении, то есть показали бы одну сумму двумя
 * разными числами.
 */
import type { CalendarDay } from '@/calendar/api';
import { t } from '@/i18n';
import { pnlToneClass } from '@/journal/position-view';
import { decimalSign, formatMoney } from '@/lib/decimal';

export type MoneyView = {
  readonly text: string;
  /** Класс цвета: зелёный/красный/серый (SPEC.md 9.4). */
  readonly tone: string;
};

/** Метка и цвет счёта для разбивки. Берутся из списка счетов, а не из ответа календаря. */
export type AccountBrief = {
  readonly id: string;
  readonly label: string;
  readonly color: string;
};

export type AccountLine = {
  readonly id: string;
  readonly label: string;
  readonly color: string;
  readonly trades: number;
  readonly money: MoneyView;
};

export function moneyView(raw: string): MoneyView {
  return {
    text: formatMoney(raw) ?? t.calendar.unknownValue,
    tone: pnlToneClass(decimalSign(raw) ?? 'zero'),
  };
}

/**
 * Разбивка дня по счетам — SPEC.md 9.3, «при нескольких счетах».
 *
 * Пустой список у дня с одним счётом не случайность: разбивка из одной строки повторяла
 * бы сумму дня другими словами. Счёт, которого нет в списке (архивирован или удалён,
 * пока экран был открыт), показывается с честной подписью вместо выдуманной метки —
 * молча пропустить его нельзя, иначе сумма строк перестала бы сходиться с суммой дня.
 */
export function accountLines(
  day: CalendarDay,
  accounts: ReadonlyMap<string, AccountBrief>,
): AccountLine[] {
  if (day.by_account.length < 2) {
    return [];
  }
  return day.by_account.map((row) => {
    const account = accounts.get(row.account_id);
    return {
      id: row.account_id,
      label: account?.label ?? t.calendar.unknownAccount,
      color: account?.color ?? 'transparent',
      trades: row.trades,
      money: moneyView(row.net_pnl),
    };
  });
}

/**
 * Подпись дня для чтения с экрана. Разбивка входит в неё текстом, потому что всплывающая
 * панель — вещь для мыши: она появляется по наведению, а у чтения с экрана наведения нет.
 * Данные при этом одни и те же, `accountLines` считает их один раз на обе стороны.
 */
export function dayAriaLabel(
  dayOfMonth: number,
  day: CalendarDay,
  lines: readonly AccountLine[],
): string {
  const label = t.calendar.dayLabel(
    dayOfMonth,
    day.trades,
    formatMoney(day.net_pnl) ?? day.net_pnl,
  );
  if (lines.length === 0) {
    return label;
  }
  const parts = lines.map((line) =>
    t.calendar.accountLine(line.label, line.trades, line.money.text),
  );
  return `${label}. ${t.calendar.breakdownLabel(parts.join('; '))}`;
}

/** Счета списком «id → метка и цвет»: разбивка ищет в нём каждый счёт своего дня. */
export function accountsById(accounts: readonly AccountBrief[]): ReadonlyMap<string, AccountBrief> {
  return new Map(accounts.map((account) => [account.id, account]));
}
