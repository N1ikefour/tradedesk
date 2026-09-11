import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, type ReactNode } from 'react';

import { installUnauthorizedBridge } from '@/auth/session';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Повторы выключены: 401 и 429 повторять нечего, а ретраи прячут ошибку от
        // пользователя за задержкой. Точечные повторы включаются на своих запросах.
        retry: false,
        // X-42. По умолчанию TanStack Query **не отправляет** запрос, пока браузер считает
        // себя офлайн: он висит в `pending`, и экран рисует «Загрузка…» без конца. Для этой
        // установки такое поведение вредит вдвойне. API здесь всегда `localhost`, и
        // «браузер офлайн» (выключенный Wi-Fi, проснувшийся ноутбук, переключённый VPN —
        // X-68) ничего не говорит о его доступности: запрос прошёл бы. А куда более частый
        // случай — обратный: сеть браузер считает живой, а `api` ещё поднимается вместе с
        // Docker Desktop, и это обычный отказ соединения, а не офлайн. Поэтому запрос
        // уходит всегда и честно падает: отказ видно, и у него есть «Повторить».
        networkMode: 'always',
        // Общий `refetchOnWindowFocus` остаётся выключенным: перечитывать удачно
        // загруженный экран на каждое переключение окна незачем. Но запрос, который упал,
        // сам себя не поднимет, и состояние залипает до F5 — а человек, дождавшийся
        // Docker Desktop, возвращается во вкладку именно за этим. Возврат во вкладку и
        // есть его «попробуй ещё раз».
        refetchOnWindowFocus: (query) => query.state.status === 'error',
      },
      // Та же причина, что у запросов, и та же цена ошибки: поставленная на паузу мутация
      // держит индикатор на «Сохранение…», то есть на «сохранено» в глазах человека
      // (найдено в S2-07 на карточке позиции).
      mutations: { retry: false, networkMode: 'always' },
    },
  });
}

/** Провайдеры приложения. Тот же состав используют тесты — иначе они проверяют не то. */
export function AppProviders({ client, children }: { client: QueryClient; children: ReactNode }) {
  useEffect(() => installUnauthorizedBridge(client), [client]);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
