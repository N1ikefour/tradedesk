import { LogOut } from 'lucide-react';
import { NavLink, useNavigate } from 'react-router';

import { ThemeToggle } from '@/components/theme-toggle';
import { Button } from '@/components/ui/button';
import { useLogout, useSession } from '@/auth/session';
import { t } from '@/i18n';
import { DEV_OUTBOX_AVAILABLE } from '@/lib/env';
import { cn } from '@/lib/utils';

const NAV_ITEMS = [
  { to: '/', label: t.nav.dashboard, end: true },
  { to: '/journal', label: t.nav.journal, end: false },
  { to: '/calendar', label: t.nav.calendar, end: false },
  { to: '/accounts', label: t.nav.accounts, end: false },
  { to: '/settings', label: t.nav.settings, end: false },
] as const;

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

        <nav aria-label={t.header.menu} className="flex min-w-0 items-center gap-1 overflow-x-auto">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  'rounded-md px-2.5 py-1.5 text-sm whitespace-nowrap transition-colors',
                  isActive
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
          {DEV_OUTBOX_AVAILABLE ? (
            <NavLink
              to="/dev/outbox"
              className={({ isActive }) =>
                cn(
                  'rounded-md px-2.5 py-1.5 text-sm whitespace-nowrap transition-colors',
                  isActive
                    ? 'bg-accent text-accent-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )
              }
            >
              {t.nav.devOutbox}
            </NavLink>
          ) : null}
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-2">
          {/*
            Место под глобальный переключатель счетов (SPEC.md 9.2). Сам переключатель
            приезжает вместе со счетами — S1-11; сейчас здесь только слот, чтобы шапка
            не перекраивалась под него задним числом. Подписи нет намеренно: слово
            «Счета» уже стоит в меню слева, и второе такое же читается как ошибка.
          */}
          <div
            data-slot="account-switcher"
            aria-hidden="true"
            title={t.header.accountSwitcherHint}
            className="hidden h-9 w-28 rounded-md border border-dashed border-border sm:block"
          />

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
