/**
 * Глобальный переключатель счетов в шапке — SPEC.md 9.2. Выбор влияет на журнал,
 * календарь и дашборд одновременно, поэтому он и живёт в шапке, а не на экране журнала.
 *
 * Выпадающий список сделан руками, без `@radix-ui/react-dropdown-menu`: поведение здесь
 * сводится к «закрыться по Escape и по клику мимо» (`lib/use-dismiss`), и ради него в
 * проект не заводится ещё одна зависимость — так же, как решено для модального окна.
 */
import { Check, ChevronDown, Plus, TriangleAlert } from 'lucide-react';
import { useCallback, useEffect, useId, useRef, useState } from 'react';

import { AccountCreateDialog } from '@/accounts/account-create-dialog';
import { useAccounts, type Account } from '@/accounts/api';
import {
  mixesDemoAndReal,
  resolveSelection,
  showsAllRealPreset,
  useAccountSelection,
  useAccountSelectionStore,
} from '@/accounts/selection';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { t } from '@/i18n';
import { useDismiss } from '@/lib/use-dismiss';
import { useMediaQuery } from '@/lib/use-media-query';
import { cn } from '@/lib/utils';

/**
 * Граница, за которой список висит на кнопке, а не на окне, — та же `sm`, что и в классах
 * ниже. До неё список приколот к окну (`fixed`), а шапка едет вместе со страницей.
 */
const ANCHORED_QUERY = '(min-width: 640px)';

function ColorDot({ color, className }: { color: string; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn('inline-block size-2.5 shrink-0 rounded-full', className)}
      style={{ backgroundColor: color }}
    />
  );
}

function AccountLine({ account }: { account: Account }) {
  return (
    <>
      <ColorDot color={account.color} />
      <span className="min-w-0 truncate">{account.label}</span>
      {account.is_demo ? (
        <Badge className="shrink-0 px-1.5 py-0 text-[10px]">{t.accountSwitcher.demoBadge}</Badge>
      ) : null}
    </>
  );
}

/** Пресет — правило, а не список галочек, поэтому и кнопка, а не чекбокс. */
function Preset({
  label,
  active,
  onSelect,
}: {
  label: string;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={cn(
        'flex flex-1 items-center justify-center gap-1.5 rounded-md border border-border px-2 py-1.5 text-sm hover:bg-accent',
        active && 'bg-accent font-medium',
      )}
      onClick={onSelect}
    >
      {active ? <Check aria-hidden="true" className="size-3.5 shrink-0" /> : null}
      <span className="min-w-0 truncate">{label}</span>
    </button>
  );
}

export function AccountSwitcher() {
  const accounts = useAccounts(false);
  const selection = useAccountSelection();
  const selectAll = useAccountSelectionStore((state) => state.selectAll);
  const selectAllReal = useAccountSelectionStore((state) => state.selectAllReal);
  const toggleId = useAccountSelectionStore((state) => state.toggleId);
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const root = useRef<HTMLDivElement | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const listId = useId();

  const anchored = useMediaQuery(ANCHORED_QUERY, true);

  useDismiss(
    open,
    root,
    trigger,
    useCallback(() => setOpen(false), []),
  );

  /**
   * На узком экране список приколот к окну, а шапка — нет: прокрутка уводит кнопку вверх,
   * и список остаётся висеть сам по себе (измерено на 375 px: при `scrollY = 73` кнопка
   * уехала на `top = -63`, список остался на `top = 64`). Прокрутка страницы — это уход от
   * переключателя, поэтому список закрывается, как и по клику мимо. Там, где он висит на
   * кнопке, закрывать нечего: он едет вместе с ней.
   */
  useEffect(() => {
    if (!open || anchored) {
      return;
    }
    const close = () => setOpen(false);
    window.addEventListener('scroll', close, { passive: true });
    return () => window.removeEventListener('scroll', close);
  }, [open, anchored]);

  if (accounts.isPending) {
    return null;
  }

  if (accounts.isError) {
    return (
      <span className="hidden text-xs text-muted-foreground sm:inline">
        {t.accountSwitcher.loadFailed}
      </span>
    );
  }

  const items = accounts.data.items;
  if (items.length === 0) {
    return null;
  }

  const resolved = resolveSelection(selection, items);
  const chosen = new Set(resolved.ids);
  const single = items.length === 1 ? items[0] : undefined;

  // SPEC.md 9.2: один счёт — переключатель показывает его без выпадающего списка.
  // Выбирать не из чего, а список из одного пункта делал бы вид, что есть из чего.
  // Заводить счета отсюда тоже нечем: без списка некуда повесить кнопку, а экран счетов
  // в одном клике по меню и на нём же лежит всё остальное про счёт.
  if (single !== undefined) {
    return (
      <span className="hidden max-w-44 items-center gap-2 rounded-md border border-border px-2.5 py-1.5 text-sm sm:inline-flex">
        <AccountLine account={single} />
      </span>
    );
  }

  const mixed = mixesDemoAndReal(resolved, items);
  const label =
    selection.mode === 'all_real'
      ? t.accountSwitcher.allReal
      : resolved.ids.length === 0
        ? t.accountSwitcher.all
        : resolved.ids.length === 1
          ? (items.find((account) => account.id === resolved.ids[0])?.label ??
            t.accountSwitcher.selected(1))
          : t.accountSwitcher.selected(resolved.ids.length);

  /**
   * Кнопка, открывающая модальное окно, уезжает из документа вместе со списком — а окно
   * запоминает, кому вернуть фокус, уже после этого, и получает `body`. Поэтому фокус
   * переводится на кнопку переключателя заранее, пока список ещё на месте.
   */
  const startCreating = () => {
    trigger.current?.focus();
    setOpen(false);
    setCreating(true);
  };

  return (
    <div ref={root} className="relative flex min-w-0 items-center gap-1.5">
      <Button
        ref={trigger}
        type="button"
        variant="outline"
        size="sm"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-label={mixed ? t.accountSwitcher.openMixed : t.accountSwitcher.open}
        onClick={() => setOpen((value) => !value)}
        // `min-w-0`: место в шапке делится, и кнопке приходится ужиматься сильнее своего
        // содержимого — иначе бейдж рядом с ней выезжает за край переключателя и ложится
        // поверх кнопки темы. Имя счёта на такой ширине обрезается многоточием.
        className="min-w-0 max-w-28 sm:max-w-44"
      >
        <span className="min-w-0 truncate">{label}</span>
        <ChevronDown aria-hidden="true" />
      </Button>

      {/* Бейдж стоит рядом с кнопкой, а не внутри: `aria-label` кнопки закрывает собой
          её содержимое, и предупреждение внутри для незрячего человека не существовало
          бы. В узкой шапке от бейджа остаётся один значок — текст и рамка там стоят
          места, которое отнимается у имени счёта на кнопке; объявленным текст остаётся
          в обеих ширинах. */}
      {mixed ? (
        <Badge
          tone="warning"
          className="shrink-0 gap-1 border-transparent bg-transparent px-0 sm:border-warning/40 sm:bg-warning/10 sm:px-1.5"
        >
          <TriangleAlert aria-hidden="true" className="size-3.5" />
          <span className="sr-only sm:not-sr-only">{t.accountSwitcher.mixedBadge}</span>
        </Badge>
      ) : null}

      {/* На узком экране список кладётся по ширине окна, а не вешается на правый край
          кнопки: 288 px от неё уезжают за левую границу страницы вместе со столбцом
          галочек, и доскроллить туда нельзя — документ шире не становится. Измерено на
          375 px: левый край списка был на −23 px. */}
      {open ? (
        <div
          id={listId}
          className="fixed inset-x-2 top-16 z-40 rounded-md border border-border bg-card p-2 shadow-lg sm:absolute sm:inset-x-auto sm:top-full sm:right-0 sm:mt-2 sm:w-72"
        >
          <div className="flex items-center gap-1">
            <Preset
              label={t.accountSwitcher.all}
              active={selection.mode === 'all'}
              onSelect={selectAll}
            />
            {showsAllRealPreset(selection, items) ? (
              <Preset
                label={t.accountSwitcher.allReal}
                active={selection.mode === 'all_real'}
                onSelect={selectAllReal}
              />
            ) : null}
          </div>

          <ul className="mt-1 flex max-h-72 flex-col gap-0.5 overflow-y-auto">
            {items.map((account) => (
              <li key={account.id}>
                <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent">
                  <input
                    type="checkbox"
                    className="size-4 shrink-0 accent-primary"
                    checked={chosen.has(account.id)}
                    // Отмеченное на экране и есть основа для щелчка (`toggleId`): пресет
                    // разворачивается в явный список, из которого счёт вычитается.
                    onChange={() => toggleId(account.id, resolved.ids)}
                  />
                  <AccountLine account={account} />
                </label>
              </li>
            ))}
          </ul>

          {mixed ? (
            <p className="mt-2 rounded-md border border-warning/40 bg-warning/10 px-2 py-1.5 text-xs text-warning">
              {t.accountSwitcher.mixedNote}
            </p>
          ) : null}

          <p className="mt-2 border-t border-border px-2 pt-2 text-xs text-muted-foreground">
            {t.accountSwitcher.hint}
          </p>

          <button
            type="button"
            className="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent"
            onClick={startCreating}
          >
            <Plus aria-hidden="true" className="size-4 shrink-0" />
            {t.accountSwitcher.add}
          </button>
        </div>
      ) : null}

      <AccountCreateDialog open={creating} onClose={() => setCreating(false)} />
    </div>
  );
}
