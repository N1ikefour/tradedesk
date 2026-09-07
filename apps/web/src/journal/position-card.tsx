/**
 * Карточка позиции — SPEC.md 9.3. Собирает блоки и отвечает за состояния запроса.
 *
 * Блока «Скриншоты» здесь нет, и это решение, а не пропуск: вложения приходят в `S2-04`,
 * а сам блок — в `S2-08`. Пустая рамка на его месте читалась бы как «не загрузилось» —
 * ровно та же причина, по которой в журнале нет заглушки под сводку (`S2-06`).
 */
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { Link } from 'react-router';
import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { messageForError } from '@/api/error-message';
import { ApiRequestError, ERROR_CODE } from '@/api/errors';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { t } from '@/i18n';
import { POSITIONS_QUERY_KEY, TAGS_QUERY_KEY, usePosition } from '@/journal/api';
import { DealsTable } from '@/journal/deals-table';
import { EntryBlocks } from '@/journal/entry-blocks';
import { PositionHeader } from '@/journal/position-header';
import { ReflectionBlock } from '@/journal/reflection-block';

export type PositionNav = {
  /** Адрес соседней карточки или `null`, если сосед неизвестен. */
  readonly prev: string | null;
  readonly next: string | null;
  /** Нашлась ли позиция в загруженном списке журнала. */
  readonly known: boolean;
  readonly backHref: string;
};

const NOT_FOUND_CODES: readonly string[] = [ERROR_CODE.positionNotFound, ERROR_CODE.notFound];

export function PositionCard({
  positionId,
  nav,
  headingLevel = 'h1',
}: {
  positionId: string;
  nav: PositionNav;
  headingLevel?: 'h1' | 'h2';
}) {
  const query = usePosition(positionId);
  const client = useQueryClient();

  /**
   * Список журнала сбрасывается один раз — когда карточку закрыли и что-то в ней
   * записали. На каждое успешное сохранение его сбрасывать нельзя: пагинация курсорная,
   * и обновление тянуло бы за собой все загруженные страницы на каждое нажатие клавиши.
   * Словарь тегов рядом: незнакомый тег заводится сохранением записи.
   */
  const onTouched = useCallback(() => {
    void client.invalidateQueries({ queryKey: POSITIONS_QUERY_KEY });
    void client.invalidateQueries({ queryKey: TAGS_QUERY_KEY });
  }, [client]);

  const notFound =
    query.error instanceof ApiRequestError &&
    query.error.code !== null &&
    NOT_FOUND_CODES.includes(query.error.code);

  return (
    <section className="flex w-full flex-col gap-4">
      <PositionNavBar nav={nav} />

      {query.isPending ? <p className="text-sm text-muted-foreground">{t.common.loading}</p> : null}

      {query.isError ? (
        <div className="flex flex-col items-start gap-3">
          <Alert variant="destructive">
            {notFound
              ? messageForError(query.error)
              : `${t.position.loadFailed} ${messageForError(query.error)}`}
          </Alert>
          {notFound ? null : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={query.isFetching}
              onClick={() => {
                void query.refetch();
              }}
            >
              {t.common.retry}
            </Button>
          )}
        </div>
      ) : null}

      {query.data === undefined ? null : (
        <>
          <PositionHeader position={query.data} headingLevel={headingLevel} />
          {/*
           * `key` здесь — не оптимизация, а условие сохранности данных. Стрелка «→»
           * меняет `positionId` под тем же деревом, и если сосед уже в кэше запроса, то
           * без ключа React оставляет блоки формы смонтированными: `useFlushOnUnmount` не
           * срабатывает, набранное переезжает на чужую позицию и записывается ей.
           * Найдено в браузере: заметка, набранная EURUSD, оказалась у USDJPY.
           */}
          <EntryBlocks key={`entry-${positionId}`} position={query.data} onTouched={onTouched} />
          <ReflectionBlock
            key={`reflection-${positionId}`}
            position={query.data}
            onTouched={onTouched}
          />
          <DealsTable deals={query.data.deals} />
        </>
      )}
    </section>
  );
}

/**
 * Навигация «← предыдущая / следующая →» по текущему списку (SPEC.md 9.3).
 *
 * Стрелка есть ровно тогда, когда сосед известен: карточка живёт внутри маршрута журнала
 * и видит те строки, что уже загружены рядом. По прямой ссылке список не загружен, и
 * тогда стрелок нет вовсе — кнопка, иногда ведущая не туда, хуже отсутствующей.
 */
function PositionNavBar({ nav }: { nav: PositionNav }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <Button asChild variant="link" size="sm" className="px-0">
        <Link to={nav.backHref}>{t.position.backToJournal}</Link>
      </Button>
      <div className="flex flex-wrap items-center gap-2">
        {!nav.known ? (
          <span className="text-xs text-muted-foreground">{t.position.neighborsHint}</span>
        ) : null}
        {nav.prev === null ? null : (
          <Button asChild variant="outline" size="sm">
            <Link to={nav.prev}>
              <ArrowLeft aria-hidden="true" />
              {t.position.prev}
            </Link>
          </Button>
        )}
        {nav.next === null ? null : (
          <Button asChild variant="outline" size="sm">
            <Link to={nav.next}>
              {t.position.next}
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
        )}
      </div>
    </div>
  );
}
