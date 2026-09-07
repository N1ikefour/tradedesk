/**
 * Экраны-заглушки маршрутов SPEC.md 9.1. Остался один — календарь (`S2-09`).
 * Счета уехали в S1-11 (`routes/accounts-page.tsx`, `routes/account-page.tsx`),
 * журнал — в S2-06 (`routes/journal-page.tsx`), карточка позиции — в S2-07
 * (`routes/position-page.tsx`), дашборд — в S2-10 (`routes/dashboard-page.tsx`).
 */
import { PageStub } from '@/components/page-stub';
import { t } from '@/i18n';

export function CalendarPage() {
  return <PageStub title={t.pages.calendar} />;
}
