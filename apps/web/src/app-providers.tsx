import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, type ReactNode } from 'react';

import { installUnauthorizedBridge } from '@/auth/session';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      // Повторы выключены: 401 и 429 повторять нечего, а ретраи прячут ошибку от
      // пользователя за задержкой. Точечные повторы включаются на своих запросах.
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

/** Провайдеры приложения. Тот же состав используют тесты — иначе они проверяют не то. */
export function AppProviders({ client, children }: { client: QueryClient; children: ReactNode }) {
  useEffect(() => installUnauthorizedBridge(client), [client]);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
