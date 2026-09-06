import type { RouteObject } from 'react-router';

import { DevOutboxPage } from '@/routes/dev-outbox-page';
import { LoginPage } from '@/routes/login-page';
import { NotFoundPage } from '@/routes/not-found-page';
import { RequireAuth } from '@/routes/require-auth';
import { RootLayout } from '@/routes/root-layout';
import { AccountPage } from '@/routes/account-page';
import { AccountsPage } from '@/routes/accounts-page';
import { JournalPage } from '@/routes/journal-page';
import { SettingsPage } from '@/routes/settings-page';
import { PositionPage } from '@/routes/position-page';
import { CalendarPage, DashboardPage } from '@/routes/stub-pages';
import { DEV_OUTBOX_AVAILABLE } from '@/lib/env';

/**
 * Маршруты SPEC.md 9.1. Один список на приложение и на тесты: расхождение между тем,
 * что проверяется, и тем, что открывается в браузере, — отдельный класс багов.
 */
export const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  // Страницы нет там, где нет эндпоинта: в проде это обычный 404 приложения.
  ...(DEV_OUTBOX_AVAILABLE ? [{ path: '/dev/outbox', element: <DevOutboxPage /> }] : []),
  {
    element: <RequireAuth />,
    children: [
      {
        element: <RootLayout />,
        children: [
          { index: true, element: <DashboardPage /> },
          // Карточка позиции — вложенный маршрут, а не соседний: SPEC.md 9.1 требует
          // модал поверх таблицы, а SPEC.md 9.3 — навигацию по текущему списку. И то и
          // другое возможно, только пока список остаётся смонтированным под карточкой.
          {
            path: 'journal',
            element: <JournalPage />,
            children: [{ path: ':id', element: <PositionPage /> }],
          },
          { path: 'calendar', element: <CalendarPage /> },
          { path: 'accounts', element: <AccountsPage /> },
          { path: 'accounts/:id', element: <AccountPage /> },
          { path: 'settings', element: <SettingsPage /> },
        ],
      },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
];
