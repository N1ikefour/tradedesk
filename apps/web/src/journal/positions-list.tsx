/**
 * Список позиций: таблица на большом экране и карточки на телефоне (SPEC.md 9.3).
 *
 * Обе раскладки виртуализированы и живут в одном контейнере прокрутки: на экране лежит
 * окно строк, а не весь журнал. Форматирование считается только для видимого окна —
 * именно поэтому длина списка почти не влияет на стоимость кадра.
 *
 * Высота строки — константа (`use-virtual-rows` считает по ней отступы), поэтому ячейки
 * не переносятся: всё лишнее обрезается, а полностью читается в карточке позиции.
 */
import { ArrowDown, ArrowUp, ImageIcon, NotebookPen } from 'lucide-react';
import { useEffect, useRef, type ReactNode } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';

import { Badge } from '@/components/ui/badge';
import { t } from '@/i18n';
import type { PositionListItem } from '@/journal/api';
import type { JournalFilters, SortField } from '@/journal/filters';
import { describePosition, pnlToneClass, type PositionView } from '@/journal/position-view';
import { useIsDesktop } from '@/lib/use-media-query';
import { useVirtualRows } from '@/lib/use-virtual-rows';
import { cn } from '@/lib/utils';

/**
 * Строка таблицы: 44 пикселя тела плюс схлопнутая рамка сверху. Рамку приходится
 * считать отдельно, потому что при `border-collapse: collapse` (его ставит preflight
 * Tailwind) она не входит в высоту `tr` так, как её понимает `box-sizing` — строка с
 * `height: 44` занимает 45. Виртуализация меряет шаг, поэтому шаг здесь и объявлен;
 * `tr` получает высоту без рамки. Замерено в браузере, закреплено тестом раскладки.
 */
const ROW_BORDER = 1;
const ROW_BODY_HEIGHT = 44;
export const ROW_HEIGHT = ROW_BODY_HEIGHT + ROW_BORDER;

/**
 * Карточка — обычный блок, а не строка таблицы: `box-sizing: border-box` из того же
 * preflight включает рамку в заданную высоту, и шаг равен ей.
 */
export const CARD_HEIGHT = 96;
const COLUMN_COUNT = 11;

type SortState = Pick<JournalFilters, 'sortField' | 'sortDirection'>;

function Marks({ view }: { view: PositionView }) {
  return (
    <span className="flex items-center gap-1.5 text-muted-foreground">
      {view.hasReflection ? (
        <NotebookPen className="size-4" aria-label={t.journal.reflectionMark} />
      ) : null}
      {view.hasAttachments ? (
        <ImageIcon className="size-4" aria-label={t.journal.attachmentsMark} />
      ) : null}
    </span>
  );
}

function Tags({ tags }: { tags: readonly string[] }) {
  if (tags.length === 0) {
    return null;
  }
  return (
    <span className="flex min-w-0 items-center gap-1 overflow-hidden">
      {tags.map((tag) => (
        <Badge key={tag} className="max-w-24 truncate px-1.5 py-0 text-[10px]">
          {tag}
        </Badge>
      ))}
    </span>
  );
}

function SortableHeader({
  field,
  label,
  sort,
  onSort,
  className,
}: {
  field: SortField;
  label: string;
  sort: SortState;
  onSort: (field: SortField) => void;
  className?: string;
}) {
  const active = sort.sortField === field;
  return (
    <th
      scope="col"
      aria-sort={active ? (sort.sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}
      className={cn('px-2 py-2 text-left font-medium', className)}
    >
      <button
        type="button"
        className="inline-flex items-center gap-1 hover:text-foreground"
        aria-label={t.journal.sortBy(label)}
        onClick={() => onSort(field)}
      >
        <span className={cn(active ? 'text-foreground' : undefined)}>{label}</span>
        {active ? (
          sort.sortDirection === 'asc' ? (
            <ArrowUp className="size-3" aria-hidden="true" />
          ) : (
            <ArrowDown className="size-3" aria-hidden="true" />
          )
        ) : null}
      </button>
    </th>
  );
}

function Spacer({ height }: { height: number }) {
  if (height <= 0) {
    return null;
  }
  return (
    <tr aria-hidden="true" style={{ height }}>
      <td colSpan={COLUMN_COUNT} />
    </tr>
  );
}

function Row({ view, onOpen }: { view: PositionView; onOpen: (href: string) => void }) {
  return (
    <tr
      style={{ height: ROW_BODY_HEIGHT }}
      className="cursor-pointer border-t border-border hover:bg-accent/50"
      onClick={(event) => {
        // Клик по самой ссылке роутер обрабатывает сам — второй переход здесь лишний.
        if ((event.target as HTMLElement).closest('a') === null) {
          onOpen(view.href);
        }
      }}
    >
      <td className="p-0">
        <span
          aria-hidden="true"
          title={view.accountTitle}
          className="block w-1.5"
          style={{ backgroundColor: view.accountColor, height: ROW_BODY_HEIGHT }}
        />
      </td>
      <td
        className="truncate px-2 whitespace-nowrap"
        title={view.isOpen ? t.journal.openedAt(view.openTime) : undefined}
      >
        {view.isOpen ? (
          <Badge tone="warning" className="px-1.5 py-0 text-[10px]">
            {t.journal.stillOpen}
          </Badge>
        ) : (
          view.closeTime
        )}
      </td>
      <td className="truncate px-2 font-medium whitespace-nowrap">
        <Link
          to={view.href}
          aria-label={t.journal.openCard(view.symbol)}
          className="hover:underline"
        >
          {view.symbol}
        </Link>
      </td>
      <td className="truncate px-2 whitespace-nowrap">{view.directionLabel}</td>
      <td className="truncate px-2 text-right whitespace-nowrap tabular-nums">{view.volume}</td>
      <td className="truncate px-2 whitespace-nowrap tabular-nums text-muted-foreground">
        {view.entryPrice} → {view.exitPrice}
      </td>
      <td className="truncate px-2 whitespace-nowrap text-muted-foreground">{view.duration}</td>
      <td
        className={cn(
          'truncate px-2 text-right font-medium whitespace-nowrap tabular-nums',
          pnlToneClass(view.netPnlSign),
        )}
      >
        {view.netPnl}
      </td>
      <td className="truncate px-2 text-right whitespace-nowrap tabular-nums">
        {view.ratio ?? t.journal.unknownValue}
      </td>
      <td className="max-w-0 truncate px-2">
        <Tags tags={view.tags} />
      </td>
      <td className="px-2">
        <Marks view={view} />
      </td>
    </tr>
  );
}

function Card({ view, onOpen }: { view: PositionView; onOpen: (href: string) => void }) {
  return (
    <li
      style={{ height: CARD_HEIGHT }}
      className="flex cursor-pointer flex-col justify-center gap-1 border-t border-border px-3"
      onClick={(event) => {
        if ((event.target as HTMLElement).closest('a') === null) {
          onOpen(view.href);
        }
      }}
    >
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="size-2.5 shrink-0 rounded-full"
          style={{ backgroundColor: view.accountColor }}
        />
        <Link
          to={view.href}
          aria-label={t.journal.openCard(view.symbol)}
          className="truncate font-medium hover:underline"
        >
          {view.symbol}
        </Link>
        <span className="shrink-0 text-xs text-muted-foreground">{view.directionLabel}</span>
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{view.volume}</span>
        <span
          className={cn('ml-auto shrink-0 font-medium tabular-nums', pnlToneClass(view.netPnlSign))}
        >
          {view.netPnl}
        </span>
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span className="shrink-0">
          {view.isOpen ? t.journal.openedAt(view.openTime) : view.closeTime}
        </span>
        <span className="truncate tabular-nums">
          {view.entryPrice} → {view.exitPrice}
        </span>
        <span className="shrink-0">{view.duration}</span>
        <span className="ml-auto flex shrink-0 items-center gap-1.5">
          {view.ratio === null ? null : <span className="tabular-nums">{view.ratio} R</span>}
          <Marks view={view} />
        </span>
      </div>
    </li>
  );
}

export function PositionsList({
  items,
  timeZone,
  sort,
  onSortChange,
  onReachEnd,
  footer,
}: {
  items: readonly PositionListItem[];
  timeZone: string;
  sort: SortState;
  onSortChange: (field: SortField) => void;
  onReachEnd: () => void;
  footer: ReactNode;
}) {
  const isDesktop = useIsDesktop();
  const container = useRef<HTMLDivElement | null>(null);
  const navigate = useNavigate();
  const { search } = useLocation();
  const virtual = useVirtualRows({
    count: items.length,
    rowHeight: isDesktop ? ROW_HEIGHT : CARD_HEIGHT,
    containerRef: container,
  });

  const { end } = virtual;
  useEffect(() => {
    // Догрузка идёт от окна прокрутки, а не от кнопки: страница в 50 строк заканчивается
    // быстрее, чем человек успевает решить, что список кончился.
    if (items.length > 0 && end >= items.length) {
      onReachEnd();
    }
  }, [end, items.length, onReachEnd]);

  const views = items
    .slice(virtual.start, virtual.end)
    .map((item) => describePosition(item, timeZone, search));
  const open = (href: string) => {
    void navigate(href);
  };

  return (
    <div
      ref={container}
      onScroll={virtual.onScroll}
      className="max-h-[68vh] min-h-64 overflow-auto rounded-lg border border-border"
    >
      {isDesktop ? (
        <table className="w-full table-fixed text-sm">
          <colgroup>
            <col className="w-1.5" />
            <col className="w-32" />
            <col className="w-28" />
            <col className="w-20" />
            <col className="w-20" />
            <col className="w-36" />
            <col className="w-24" />
            <col className="w-28" />
            <col className="w-14" />
            <col />
            <col className="w-16" />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-card text-xs text-muted-foreground">
            <tr>
              <th scope="col" aria-label={t.journal.columnAccount} />
              <SortableHeader
                field="close_time"
                label={t.journal.columnCloseTime}
                sort={sort}
                onSort={onSortChange}
              />
              <SortableHeader
                field="symbol_norm"
                label={t.journal.columnSymbol}
                sort={sort}
                onSort={onSortChange}
              />
              <th scope="col" className="px-2 py-2 text-left font-medium">
                {t.journal.columnDirection}
              </th>
              <th scope="col" className="px-2 py-2 text-right font-medium">
                {t.journal.columnVolume}
              </th>
              <th scope="col" className="px-2 py-2 text-left font-medium">
                {t.journal.columnPrices}
              </th>
              <SortableHeader
                field="duration_seconds"
                label={t.journal.columnDuration}
                sort={sort}
                onSort={onSortChange}
              />
              <SortableHeader
                field="net_pnl"
                label={t.journal.columnNetPnl}
                sort={sort}
                onSort={onSortChange}
                className="text-right"
              />
              <th scope="col" className="px-2 py-2 text-right font-medium">
                {t.journal.columnRatio}
              </th>
              <th scope="col" className="px-2 py-2 text-left font-medium">
                {t.journal.columnTags}
              </th>
              <th scope="col" className="px-2 py-2 text-left font-medium">
                {t.journal.columnMarks}
              </th>
            </tr>
          </thead>
          <tbody>
            <Spacer height={virtual.paddingTop} />
            {views.map((view) => (
              <Row key={view.id} view={view} onOpen={open} />
            ))}
            <Spacer height={virtual.paddingBottom} />
          </tbody>
        </table>
      ) : (
        <ul>
          <li aria-hidden="true" style={{ height: virtual.paddingTop }} />
          {views.map((view) => (
            <Card key={view.id} view={view} onOpen={open} />
          ))}
          <li aria-hidden="true" style={{ height: virtual.paddingBottom }} />
        </ul>
      )}
      {footer}
    </div>
  );
}
