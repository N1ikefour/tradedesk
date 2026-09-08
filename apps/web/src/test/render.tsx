import type { QueryClient } from '@tanstack/react-query';
import { render, type RenderResult } from '@testing-library/react';
import { RouterProvider, createMemoryRouter, type RouterProviderProps } from 'react-router';

import { AppProviders, createQueryClient } from '@/app-providers';
import type { SessionUser } from '@/auth/session';
import { routes } from '@/routes/routes';

/** Пользователь из схемы API — форма та же, что придёт с сервера. */
export const TEST_USER: SessionUser = {
  id: '0199a2b0-0000-7000-8000-000000000001',
  email: 'trader@example.com',
  display_name: null,
  timezone: 'Asia/Yekaterinburg',
  day_boundary_hour: 0,
};

/**
 * Приложение целиком на памяти роутера: тот же список маршрутов и те же провайдеры,
 * что в браузере (`src/app.tsx`).
 */
export function renderApp(
  initialEntries: string[] = ['/'],
): RenderResult & { client: QueryClient; router: RouterProviderProps['router'] } {
  const client = createQueryClient();
  const router = createMemoryRouter(routes, { initialEntries });
  const result = render(
    <AppProviders client={client}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  // Роутер отдаётся наружу ради адреса: `router.state.location` — единственное место, где
  // видно, что экран с ним сделал. Окна у памяти роутера нет, `window.location` не при чём.
  return Object.assign(result, { client, router });
}
