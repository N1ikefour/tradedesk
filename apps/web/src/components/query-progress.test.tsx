import { QueryClientProvider, useQuery } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { createQueryClient } from '@/app-providers';
import { QueryProgress } from '@/components/query-progress';
import { t } from '@/i18n';
import { setTabHidden } from '@/test/tab-visibility';

afterEach(() => {
  setTabHidden(false);
});

/**
 * Хозяин написан как настоящие вызывающие: `isPending` решает, показывать ли ожидание,
 * а словами его называет `QueryProgress`. Состояние берётся у самой библиотеки, а не
 * подставляется пропом: `fetchStatus: 'paused'` выставляет ретраер, и проверять надо
 * именно его путь.
 */
function Host({ queryFn, retry }: { queryFn: () => Promise<string>; retry: number }) {
  const query = useQuery({ queryKey: ['probe'], queryFn, retry, retryDelay: 0 });
  return query.isPending ? <QueryProgress fetchStatus={query.fetchStatus} /> : <p>{query.data}</p>;
}

function renderHost(props: { queryFn: () => Promise<string>; retry: number }) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <Host {...props} />
    </QueryClientProvider>,
  );
}

describe('ожидание запроса словами', () => {
  it('идущий запрос — это «Загрузка…»', async () => {
    renderHost({ queryFn: () => new Promise<string>(() => {}), retry: 0 });

    expect(await screen.findByText(t.common.loading)).toBeInTheDocument();
  });

  it('приостановленный повтор называет себя паузой, а не загрузкой', async () => {
    // Повтор ждёт `focusManager.isFocused()`: пока вкладка в фоне, запрос стоит и сам не
    // сдвинется. Под общей «Загрузка…» это выглядело зависшим приложением.
    setTabHidden(true);
    renderHost({
      queryFn: () => Promise.reject(new Error('сервер молчит')),
      retry: 1,
    });

    expect(await screen.findByText(t.common.paused)).toBeInTheDocument();
    expect(screen.queryByText(t.common.loading)).not.toBeInTheDocument();
  });
});
