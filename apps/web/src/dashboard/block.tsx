/**
 * Оболочка блока дашборда и его состояния. Загрузка, серверная ошибка с кнопкой
 * «Повторить» и пустое состояние выглядят одинаково во всех четырёх блоках: разъехавшись,
 * они читались бы как разные виды поломки.
 */
import type { FetchStatus } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { messageForError } from '@/api/error-message';
import { QueryProgress } from '@/components/query-progress';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { t } from '@/i18n';

export function DashboardBlock({
  title,
  hint,
  action,
  children,
}: {
  title: string;
  hint?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    // `min-w-0`: у элемента сетки минимальная ширина по умолчанию равна содержимому,
    // поэтому широкая таблица внутри (открытые позиции) растягивала бы карточку, и
    // горизонтально ехала бы вся страница вместо самой таблицы в своей рамке.
    <Card className="min-w-0">
      <CardContent className="flex flex-col gap-3 p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 className="text-sm font-medium">{title}</h2>
          {action}
        </div>
        {hint === undefined ? null : <p className="text-xs text-muted-foreground">{hint}</p>}
        {children}
      </CardContent>
    </Card>
  );
}

export type BlockQueryState = {
  readonly isPending: boolean;
  readonly isError: boolean;
  readonly error: Error | null;
  readonly isFetching: boolean;
  readonly fetchStatus: FetchStatus;
  readonly refetch: () => void;
};

/**
 * Состояние запроса блока. Возвращает `null`, когда показывать нечего — то есть данные
 * пришли и рисует их сам блок.
 */
export function BlockStatus({
  query,
  failedMessage,
}: {
  query: BlockQueryState;
  failedMessage: string;
}) {
  if (query.isError) {
    return (
      <div className="flex flex-col items-start gap-2">
        <Alert variant="destructive">
          {failedMessage} {messageForError(query.error)}
        </Alert>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={query.isFetching}
          onClick={query.refetch}
        >
          {t.common.retry}
        </Button>
      </div>
    );
  }
  if (query.isPending) {
    return <QueryProgress fetchStatus={query.fetchStatus} />;
  }
  return null;
}
