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
 * ⚠️ Итогов недели в списке нет вовсе, хотя SPEC.md 9.3 требует их справа: недели в списке
 * нет как сущности — строки идут подряд, только с торговыми днями, и приписать итог
 * «справа от недели» не к чему. Итог месяца при этом на месте (`MonthTotals` над сеткой),
 * так что на телефоне теряется именно недельный разрез.
 *
 * Наведения нет не только на телефоне: планшет шире 768 px получает сетку, но раскрыть
 * панель разбивки пальцем не может — тап по ячейке уходит в журнал, а фокус там не
 * задерживается. Поэтому там, где указатель не умеет наводиться (`useCanHover`), у дня с
 * разбивкой появляется кнопка, открывающая ту же панель нажатием. Сетка при этом остаётся:
 * отдать планшету список значило бы отнять у него и месячную сетку, и итоги недель ради
 * панели, которая на его ширине помещается рядом.
 *
 * Различие вариантов — только в плотности и в двух добавках полного экрана: итоги недель
 * справа (SPEC.md 9.3) и разбивка дня по счетам.
 */
import { ChevronDown } from 'lucide-react';
import { useState } from 'react';
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
import { useCanHover, useIsDesktop } from '@/lib/use-media-query';
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

function Breakdown({
  lines,
  className,
  id,
  exposed = false,
}: {
  lines: readonly AccountLine[];
  className?: string;
  id?: string;
  /**
   * Панель раскрыта кнопкой и потому доступна чтению с экрана. По умолчанию нет: та же
   * разбивка уже есть в подписи ссылки (`dayAriaLabel`), а панель, появляющаяся по
   * наведению, вторым голосом читалась бы всегда — включая моменты, когда её не видно.
   */
  exposed?: boolean;
}) {
  return (
    <div
      id={id}
      aria-hidden={exposed ? undefined : 'true'}
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

/**
 * Раскрытие разбивки нажатием — для указателя, который не умеет наводиться. `undefined`
 * означает «наведение есть»: кнопка рядом с мышью была бы лишним элементом в ячейке.
 */
type Disclosure = {
  readonly open: boolean;
  readonly toggle: () => void;
};

function Cell({
  cell,
  today,
  variant,
  accounts,
  placement = DEFAULT_PLACEMENT,
  disclosure,
}: {
  cell: CalendarCell;
  today: string;
  variant: MonthViewVariant;
  accounts: ReadonlyMap<string, AccountBrief>;
  placement?: Placement;
  disclosure?: Disclosure;
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
  const open = disclosure?.open ?? false;
  const panelId = `breakdown-${cell.iso}`;
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
        <>
          {disclosure === undefined ? null : (
            // Кнопка лежит поверх ссылки, а не внутри неё: внутри ссылки нажатие ушло бы
            // в журнал вместе с ней. 24 px — минимум WCAG 2.2 для цели нажатия и заодно
            // предел: в ячейке шириной с палец большая накрыла бы саму сумму дня.
            <button
              type="button"
              aria-expanded={open}
              aria-controls={panelId}
              aria-label={t.calendar.breakdownToggle(cell.dayOfMonth)}
              onClick={disclosure.toggle}
              className="absolute right-0.5 top-0.5 z-30 flex size-6 items-center justify-center rounded text-muted-foreground hover:bg-accent"
            >
              <ChevronDown
                aria-hidden="true"
                className={cn('size-3.5 transition-transform', open && 'rotate-180')}
              />
            </button>
          )}
          {/* Панель появляется по наведению и по приходу фокуса на ссылку: клавиатура не
              наводит мышь, а без фокуса разбивка была бы доступна только ей. Раскрытая
              нажатием, она перестаёт быть прозрачной для нажатий: панель накрывает соседние
              дни, и тап по ней проваливался бы в чужой день. */}
          <Breakdown
            id={panelId}
            lines={lines}
            exposed={open}
            className={cn(
              'pointer-events-none absolute z-20 w-max max-w-[18rem] opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100',
              placement.openUp ? 'bottom-full mb-1' : 'top-full mt-1',
              placement.alignRight ? 'right-0' : 'left-0',
              open && 'pointer-events-auto opacity-100',
            )}
          />
        </>
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
  canHover,
}: {
  weeks: readonly CalendarWeek[];
  title: string;
  today: string;
  variant: MonthViewVariant;
  accounts: ReadonlyMap<string, AccountBrief>;
  canHover: boolean;
}) {
  const withTotals = variant === 'full';
  // Открыт один день на месяц, а не каждый сам по себе: панель шире ячейки и накрывает
  // соседей, поэтому две раскрытые сразу перекрыли бы друг друга.
  const [openDay, setOpenDay] = useState<string | null>(null);
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
                      disclosure={
                        canHover
                          ? undefined
                          : {
                              open: openDay === cell.iso,
                              toggle: () =>
                                setOpenDay((current) => (current === cell.iso ? null : cell.iso)),
                            }
                      }
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
  const canHover = useCanHover();
  if (isDesktop) {
    return (
      <MonthGrid
        weeks={weeks}
        title={title}
        today={today}
        variant={variant}
        accounts={accounts}
        canHover={canHover}
      />
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
