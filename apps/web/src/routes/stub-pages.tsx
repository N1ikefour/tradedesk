/**
 * Экраны-заглушки маршрутов SPEC.md 9.1. Каждый уедет в свою задачу:
 * Dashboard — S2-10, карточка позиции — S2-07, календарь — S2-09.
 * Счета уехали в S1-11 (`routes/accounts-page.tsx`, `routes/account-page.tsx`),
 * журнал — в S2-06 (`routes/journal-page.tsx`).
 */
import { PageStub } from '@/components/page-stub';
import { t } from '@/i18n';

export function DashboardPage() {
  return <PageStub title={t.pages.dashboard} />;
}

export function PositionPage() {
  return <PageStub title={t.pages.position} />;
}

export function CalendarPage() {
  return <PageStub title={t.pages.calendar} />;
}
