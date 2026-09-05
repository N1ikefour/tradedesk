/**
 * Экраны-заглушки маршрутов SPEC.md 9.1. Каждый уедет в свою задачу:
 * Dashboard — S2-10, журнал и карточка позиции — S2-06, календарь — S2-09,
 * счета — S1-11.
 */
import { PageStub } from '@/components/page-stub';
import { t } from '@/i18n';

export function DashboardPage() {
  return <PageStub title={t.pages.dashboard} />;
}

export function JournalPage() {
  return <PageStub title={t.pages.journal} />;
}

export function PositionPage() {
  return <PageStub title={t.pages.position} />;
}

export function CalendarPage() {
  return <PageStub title={t.pages.calendar} />;
}

export function AccountsPage() {
  return <PageStub title={t.pages.accounts} />;
}

export function AccountPage() {
  return <PageStub title={t.pages.account} />;
}
