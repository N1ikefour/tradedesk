/**
 * Глобальный переключатель счетов в шапке — SPEC.md 9.2. Выбор влияет на журнал,
 * календарь и дашборд одновременно, поэтому он и живёт в шапке, а не на экране журнала.
 *
 * Пресеты («Все реальные») и предупреждение «демо и реал вместе» — `S2-11`.
 *
 * Выпадающий список сделан руками, без `@radix-ui/react-dropdown-menu`: поведение здесь
 * сводится к «закрыться по Escape и по клику мимо» (`lib/use-dismiss`), и ради него в
 * проект не заводится ещё одна зависимость — так же, как решено для модального окна.
 */
import { ChevronDown } from 'lucide-react';
import { useCallback, useId, useRef, useState } from 'react';

import { useAccounts, type Account } from '@/accounts/api';
import {
  resolveSelection,
  useAccountSelection,
  useAccountSelectionStore,
} from '@/accounts/selection';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { t } from '@/i18n';
import { useDismiss } from '@/lib/use-dismiss';
import { cn } from '@/lib/utils';

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

export function AccountSwitcher() {
  const accounts = useAccounts(false);
  const selection = useAccountSelection();
  const selectAll = useAccountSelectionStore((state) => state.selectAll);
  const toggleId = useAccountSelectionStore((state) => state.toggleId);
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const listId = useId();

  useDismiss(
    open,
    root,
    trigger,
    useCallback(() => setOpen(false), []),
  );

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
  if (single !== undefined) {
    return (
      <span className="hidden max-w-44 items-center gap-2 rounded-md border border-border px-2.5 py-1.5 text-sm sm:inline-flex">
        <AccountLine account={single} />
      </span>
    );
  }

  const label =
    resolved.ids.length === 0
      ? t.accountSwitcher.all
      : resolved.ids.length === 1
        ? (items.find((account) => account.id === resolved.ids[0])?.label ??
          t.accountSwitcher.selected(1))
        : t.accountSwitcher.selected(resolved.ids.length);

  return (
    <div ref={root} className="relative min-w-0">
      <Button
        ref={trigger}
        type="button"
        variant="outline"
        size="sm"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-label={t.accountSwitcher.open}
        onClick={() => setOpen((value) => !value)}
        className="max-w-28 sm:max-w-44"
      >
        <span className="min-w-0 truncate">{label}</span>
        <ChevronDown aria-hidden="true" />
      </Button>

      {open ? (
        <div
          id={listId}
          className="absolute right-0 z-40 mt-2 w-72 rounded-md border border-border bg-card p-2 shadow-lg"
        >
          <button
            type="button"
            className={cn(
              'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent',
              resolved.ids.length === 0 && 'font-medium',
            )}
            onClick={() => selectAll()}
          >
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={resolved.ids.length === 0}
              readOnly
              tabIndex={-1}
              aria-hidden="true"
            />
            {t.accountSwitcher.all}
          </button>

          <ul className="mt-1 flex max-h-72 flex-col gap-0.5 overflow-y-auto">
            {items.map((account) => (
              <li key={account.id}>
                <label className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent">
                  <input
                    type="checkbox"
                    className="size-4 shrink-0 accent-primary"
                    checked={chosen.has(account.id)}
                    onChange={() => toggleId(account.id)}
                  />
                  <AccountLine account={account} />
                </label>
              </li>
            ))}
          </ul>

          <p className="mt-2 border-t border-border px-2 pt-2 text-xs text-muted-foreground">
            {t.accountSwitcher.hint}
          </p>
        </div>
      ) : null}
    </div>
  );
}
