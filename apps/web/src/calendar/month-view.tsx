/**
 * Месяц календаря — общий показ для экрана `/calendar` (`S2-09`) и календаря-мини
 * дашборда (`S2-10`). Один компонент, а не два похожих: дни, ссылки и суммы обязаны быть
 * теми же самыми, иначе человек увидит в мини одно число, а на экране календаря другое.
 *
 * ⚠️ Границы дня приходят с сервера (`starts_at`/`ends_at`) и подставляются в журнал как
 * есть (`calendar/day-link.ts`). Прямое следствие: день, которого нет в ответе, ссылкой
 * не становится — границ у него нет, и вычислить их здесь означало бы завести второе
 * правило торгового дня.
 *
 * Раскладок две, и это не украшение. В сетке из семи колонок ячейка на телефоне шириной
 * около 50 px, а `-1 779,72 $` требует полутора таких: сумма обрезалась бы, а обрезанные
 * деньги хуже отсутствующих — их читают как другое число. Горизонтальная прокрутка тут не
 * лечит (месяц перестаёт быть виден целиком), поэтому ниже 768 px — той же границы, что у
 * журнала (SPEC.md 9.3), — месяц показывается списком торговых дней во всю ширину строки.
 * Дни, ссылки и суммы в обеих раскладках одни и те же, считаны одним `buildMonthGrid`.
 *
 * Различие вариантов — только в плотности и в двух добавках полного экрана: итоги недель
 * справа (SPEC.md 9.3) и разбивка дня по счетам.
 */
import { Link } from 'react-router';

import type { CalendarDay } from '@/calendar/api';
import { journalDayLink } from '@/calendar/day-link';
import {
  accountLines,
  dayAriaLabel,
  moneyView,
  type AccountBrief,
  type AccountLine,
} from '@/calendar/day-view';
import {
  tradedCells,
  type CalendarCell,
  type CalendarWeek,
  type TradedCell,
} from '@/calendar/grid';
import { weekTotals, type CalendarTotals } from '@/calendar/totals';
import { t } from '@/i18n';
import { useIsDesktop } from '@/lib/use-media-query';
import { cn } from '@/lib/utils';

export type MonthViewVariant = 'mini' | 'full';

const STYLE = {
  mini: {
    table: 'min-w-[480px]',
    cell: 'h-16 gap-0.5 p-1.5',
    dayNumber: 'text-[11px]',
    // 11 px, а не 12: на самом узком настольном экране (768 px) ячейка держит 81 px, и
    // лишний кегль обрезал бы уже пятизначную сумму дня.
    money: 'text-[11px]',
    trades: 'text-[10px]',
  },
  full: {
    table: 'min-w-[720px]',
    cell: 'h-24 gap-1 p-2',
    dayNumber: 'text-xs',
    money: 'text-sm',
    trades: 'text-[11px]',
  },
} as const;

const EMPTY_ACCOUNTS: ReadonlyMap<string, AccountBrief> = new Map();

function Breakdown({ lines, className }: { lines: readonly AccountLine[]; className?: string }) {
  return (
    // Для чтения с экрана та же разбивка уже есть в подписи ссылки (`dayAriaLabel`):
    // всплывающая панель — вещь для мыши, и читать её вторым голосом незачем.
    <div
      aria-hidden="true"
      className={cn('rounded-md border border-border bg-popover p-2 text-xs shadow-md', className)}
    >
      <p className="pb-1 text-[11px] text-muted-foreground">{t.calendar.breakdownTitle}</p>
      <ul className="flex flex-col gap-1">
        {lines.map((line) => (
          <li key={line.id} className="flex items-center gap-2 whitespace-nowrap">
            <span
              className="size-2 shrink-0 rounded-full"
              style={{ backgroundColor: line.color }}
            />
            <span className="min-w-0 flex-1 truncate">{line.label}</span>
            <span className="shrink-0 text-muted-foreground">{t.calendar.trades(line.trades)}</span>
            <span className={cn('shrink-0 tabular-nums', line.money.tone)}>{line.money.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DayBody({
  cell,
  day,
  variant,
  isToday,
}: {
  cell: CalendarCell;
  day: CalendarDay | null;
  variant: MonthViewVariant;
  isToday: boolean;
}) {
  const style = STYLE[variant];
  const sum = day === null ? null : moneyView(day.net_pnl);
  return (
    <>
      <span
        className={cn(
          style.dayNumber,
          isToday ? 'font-semibold text-foreground' : 'text-muted-foreground',
        )}
      >
        {cell.dayOfMonth}
        {isToday ? <span className="sr-only"> ({t.calendar.today})</span> : null}
      </span>
      {day === null || sum === null ? null : (
        <>
          <span className={cn('truncate font-medium tabular-nums', style.money, sum.tone)}>
            {sum.text}
          </span>
          <span className={cn('text-muted-foreground', style.trades)}>
            {t.calendar.trades(day.trades)}
          </span>
        </>
      )}
    </>
  );
}

/**
 * Куда раскрывается панель разбивки. Обёртка таблицы прокручивается по горизонтали, а
 * `overflow-x: auto` по правилам CSS делает `auto` и вертикальную ось: панель, вышедшая за
 * край обёртки, обрезается. Измерено в браузере — поэтому у последней строки она
 * раскрывается вверх, а у двух последних колонок прижимается к правому краю ячейки.
 */
type Placement = {
  readonly openUp: boolean;
  readonly alignRight: boolean;
};

const DEFAULT_PLACEMENT: Placement = { openUp: false, alignRight: false };

/** Суббота и воскресенье: панель шириной с треть таблицы иначе уходит за её правый край. */
const RIGHT_ALIGNED_FROM = 5;

function Cell({
  cell,
  today,
  variant,
  accounts,
  placement = DEFAULT_PLACEMENT,
}: {
  cell: CalendarCell;
  today: string;
  variant: MonthViewVariant;
  accounts: ReadonlyMap<string, AccountBrief>;
  placement?: Placement;
}) {
  const isToday = cell.iso === today;
  const day = cell.day;
  const box = cn(
    'flex flex-col justify-start rounded-md border',
    STYLE[variant].cell,
    isToday ? 'border-ring' : 'border-border',
  );

  if (day === null) {
    return (
      <div className={cn(box, 'bg-muted/20')}>
        <DayBody cell={cell} day={null} variant={variant} isToday={isToday} />
      </div>
    );
  }

  const lines = variant === 'full' ? accountLines(day, accounts) : [];
  return (
    <div className="group relative">
      <Link
        to={journalDayLink(day.starts_at, day.ends_at)}
        aria-label={dayAriaLabel(cell.dayOfMonth, day, lines)}
        className={cn(box, 'hover:bg-accent/50')}
      >
        <DayBody cell={cell} day={day} variant={variant} isToday={isToday} />
      </Link>
      {lines.length === 0 ? null : (
        // Панель появляется по наведению и по приходу фокуса на ссылку: клавиатура не
        // наводит мышь, а без фокуса разбивка была бы доступна только ей.
        <Breakdown
          lines={lines}
          className={cn(
            'pointer-events-none absolute z-20 w-max max-w-[18rem] opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100',
            placement.openUp ? 'bottom-full mb-1' : 'top-full mt-1',
            placement.alignRight ? 'right-0' : 'left-0',
          )}
        />
      )}
    </div>
  );
}

function WeekTotalCell({ totals }: { totals: CalendarTotals }) {
  if (totals.days === 0) {
    // Неделя без единой закрытой сделки — это отсутствие итога, а не итог «0,00 $».
    return <td />;
  }
  // `null` — итог не сложился: среди дней недели попался нечитаемый `net_pnl`, и сумма
  // остальных была бы неотличима от верной.
  const sum = totals.netPnl === null ? null : moneyView(totals.netPnl);
  return (
    <td className="px-2 text-right">
      <span
        className={cn(
          'block text-sm font-medium tabular-nums',
          sum?.tone ?? 'text-muted-foreground',
        )}
      >
        {sum?.text ?? t.calendar.unknownValue}
      </span>
      <span className="block text-[11px] text-muted-foreground">
        {t.calendar.trades(totals.trades)}
      </span>
    </td>
  );
}

function MonthGrid({
  weeks,
  title,
  today,
  variant,
  accounts,
}: {
  weeks: readonly CalendarWeek[];
  title: string;
  today: string;
  variant: MonthViewVariant;
  accounts: ReadonlyMap<string, AccountBrief>;
}) {
  const withTotals = variant === 'full';
  return (
    <div className="overflow-x-auto">
      <table
        className={cn('w-full table-fixed border-separate border-spacing-1', STYLE[variant].table)}
      >
        <caption className="sr-only">{title}</caption>
        <thead>
          <tr>
            {t.calendar.weekdays.map((weekday) => (
              <th
                key={weekday}
                scope="col"
                className="pb-1 text-center text-[11px] font-normal text-muted-foreground"
              >
                {weekday}
              </th>
            ))}
            {withTotals ? (
              <th
                scope="col"
                className="w-28 pb-1 text-right text-[11px] font-normal text-muted-foreground"
              >
                {t.calendar.weekTotal}
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {weeks.map((week, weekIndex) => (
            <tr key={`week-${weekIndex}`}>
              {week.map((cell, dayIndex) =>
                cell === null ? (
                  <td key={`empty-${weekIndex}-${dayIndex}`} />
                ) : (
                  <td key={cell.iso}>
                    <Cell
                      cell={cell}
                      today={today}
                      variant={variant}
                      accounts={accounts}
                      placement={{
                        openUp: weekIndex === weeks.length - 1,
                        alignRight: dayIndex >= RIGHT_ALIGNED_FROM,
                      }}
                    />
                  </td>
                ),
              )}
              {withTotals ? <WeekTotalCell totals={weekTotals(week)} /> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DayRow({
  cell,
  today,
  variant,
  accounts,
}: {
  cell: TradedCell;
  today: string;
  variant: MonthViewVariant;
  accounts: ReadonlyMap<string, AccountBrief>;
}) {
  const isToday = cell.iso === today;
  const sum = moneyView(cell.day.net_pnl);
  const lines = variant === 'full' ? accountLines(cell.day, accounts) : [];

  return (
    <li>
      <Link
        to={journalDayLink(cell.day.starts_at, cell.day.ends_at)}
        aria-label={dayAriaLabel(cell.dayOfMonth, cell.day, lines)}
        className={cn(
          'flex flex-col gap-2 rounded-md border p-2.5 hover:bg-accent/50',
          isToday ? 'border-ring' : 'border-border',
        )}
      >
        <span className="flex items-center justify-between gap-3">
          <span className="flex min-w-0 flex-col">
            <span className={cn('text-sm', isToday ? 'font-semibold' : 'font-medium')}>
              {t.calendar.rowDay(t.calendar.weekdays[cell.weekday] ?? '', cell.dayOfMonth)}
              {isToday ? <span className="sr-only"> ({t.calendar.today})</span> : null}
            </span>
            <span className="text-xs text-muted-foreground">
              {t.calendar.trades(cell.day.trades)}
            </span>
          </span>
          {/* Сумма во всю оставшуюся ширину строки: обрезать её тут нечему. */}
          <span className={cn('shrink-0 text-sm font-medium tabular-nums', sum.tone)}>
            {sum.text}
          </span>
        </span>
        {/* На телефоне наведения нет вовсе, поэтому разбивка стоит в строке открыто:
            прятать её было бы равносильно тому, чтобы её там не было. */}
        {lines.length === 0 ? null : (
          <Breakdown lines={lines} className="bg-transparent shadow-none" />
        )}
      </Link>
    </li>
  );
}

export function MonthView({
  weeks,
  title,
  today,
  variant,
  accounts = EMPTY_ACCOUNTS,
}: {
  weeks: readonly CalendarWeek[];
  title: string;
  today: string;
  variant: MonthViewVariant;
  /** Метки и цвета счетов для разбивки дня. Пусто — разбивки нет. */
  accounts?: ReadonlyMap<string, AccountBrief>;
}) {
  const isDesktop = useIsDesktop();
  if (isDesktop) {
    return (
      <MonthGrid weeks={weeks} title={title} today={today} variant={variant} accounts={accounts} />
    );
  }
  return (
    <ul className="flex flex-col gap-1.5">
      {tradedCells(weeks).map((cell) => (
        <DayRow key={cell.iso} cell={cell} today={today} variant={variant} accounts={accounts} />
      ))}
    </ul>
  );
}
