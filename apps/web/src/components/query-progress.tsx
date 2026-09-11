import type { FetchStatus } from '@tanstack/react-query';

import { t } from '@/i18n';

/**
 * Ожидание запроса словами. `fetchStatus: 'paused'` — это не «ещё грузится»: запрос не
 * идёт вовсе и сам не сдвинется, пока вкладка в фоне (X-13, X-42). Под одной «Загрузка…»
 * оба состояния выглядели одинаково, и второе читалось как зависшее приложение.
 *
 * Одно место на приложение: разъехавшись, экраны объясняли бы одно и то же по-разному.
 */
export function QueryProgress({ fetchStatus }: { fetchStatus: FetchStatus }) {
  return (
    <p className="text-sm text-muted-foreground">
      {fetchStatus === 'paused' ? t.common.paused : t.common.loading}
    </p>
  );
}
