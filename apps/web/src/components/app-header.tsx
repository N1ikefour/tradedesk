import { LogOut, Menu } from 'lucide-react';
import { useCallback, useId, useRef, useState } from 'react';
import { NavLink, useNavigate } from 'react-router';

import { AccountSwitcher } from '@/accounts/account-switcher';
import { ThemeToggle } from '@/components/theme-toggle';
import { Button } from '@/components/ui/button';
import { useLogout, useSession } from '@/auth/session';
import { t } from '@/i18n';
import { DEV_OUTBOX_AVAILABLE } from '@/lib/env';
import { useDismiss } from '@/lib/use-dismiss';
import { cn } from '@/lib/utils';

type NavItem = { readonly to: string; readonly label: string; readonly end: boolean };

const NAV_ITEMS: readonly NavItem[] = [
  { to: '/', label: t.nav.dashboard, end: true },
  { to: '/journal', label: t.nav.journal, end: false },
  { to: '/calendar', label: t.nav.calendar, end: false },
  { to: '/accounts', label: t.nav.accounts, end: false },
  { to: '/settings', label: t.nav.settings, end: false },
  // Страницы нет там, где нет эндпоинта, — см. `DEV_OUTBOX_AVAILABLE`.
  ...(DEV_OUTBOX_AVAILABLE ? [{ to: '/dev/outbox', label: t.nav.devOutbox, end: false }] : []),
];

function itemClass(isActive: boolean, extra: string): string {
  return cn(
    'rounded-md text-sm transition-colors',
    isActive ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:text-foreground',
    extra,
  );
}

/**
 * Меню шапки на узком экране (X-36).
 *
 * До `md` пункты в строку не помещаются: переключатель счетов забирает свою ширину, и от
 * меню остаётся обрубок «Даш…». Прокрутка у `nav` была и раньше, но признака у неё нет —
 * полоска читается как «пунктов больше нет», а не как «здесь есть продолжение».
 *
 * Кнопка не подписана текущим разделом намеренно: его называет заголовок страницы прямо
 * под шапкой, и вторая подпись на самом тесном экране стоила бы места, из-за которого всё
 * и затевалось.
 */
function MobileMenu() {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement | null>(null);
  const listId = useId();
  const close = useCallback(() => setOpen(false), []);

  useDismiss(open, root, close);

  return (
    <div ref={root} className="relative md:hidden">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        title={t.header.openMenu}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-label={t.header.openMenu}
        onClick={() => setOpen((value) => !value)}
      >
        <Menu aria-hidden="true" />
      </Button>

      {open ? (
        <nav
          id={listId}
          aria-label={t.header.menu}
          className="absolute left-0 z-40 mt-2 flex w-52 flex-col gap-0.5 rounded-md border border-border bg-card p-2 shadow-lg"
        >
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={close}
              className={({ isActive }) => itemClass(isActive, 'px-2 py-2 hover:bg-accent')}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      ) : null}
    </div>
  );
}

export function AppHeader() {
  const session = useSession();
  const logout = useLogout();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout.mutate(undefined, {
      onSettled: () => {
        void navigate('/login', { replace: true });
      },
    });
  };

  return (
    <header className="border-b border-border bg-card">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
        <span className="shrink-0 text-sm font-semibold tracking-tight">{t.app.name}</span>

        <MobileMenu />

        {/* `flex-1`: меню забирает свободную ширину раньше правой группы. Иначе
            переключатель счетов с длинным именем счёта съедает её, и от меню остаётся
            полоска в несколько пикселей. Прокрутка остаётся страховкой на 768–820px,
            где последний пункт обрезан наполовину и это видно. */}
        <nav
          aria-label={t.header.menu}
          className="hidden min-w-0 flex-1 items-center gap-1 overflow-x-auto md:flex"
        >
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => itemClass(isActive, 'px-2.5 py-1.5 whitespace-nowrap')}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="ml-auto flex min-w-0 shrink items-center gap-2">
          <AccountSwitcher />

          <ThemeToggle />

          {session.data ? (
            <span className="hidden max-w-44 truncate text-sm text-muted-foreground lg:inline-block lg:align-middle">
              {session.data.email}
            </span>
          ) : null}

          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleLogout}
            disabled={logout.isPending}
            aria-label={t.header.logout}
          >
            <LogOut aria-hidden="true" />
            <span className="hidden sm:inline">{t.header.logout}</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
