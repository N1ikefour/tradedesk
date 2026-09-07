/**
 * `/journal/:id` — SPEC.md 9.1: «route-модал поверх таблицы на десктопе, страница на
 * мобильном». Маршрут вложен в `/journal`, и это не оформление, а условие двух вещей:
 *
 * 1. список журнала остаётся смонтированным под модалом — иначе «поверх таблицы» не
 *    получится, а возврат к списку заново грузил бы страницы и терял прокрутку;
 * 2. навигация «← предыдущая / следующая →» имеет что читать: соседей карточка берёт из
 *    того самого списка, а не из выдуманного эндпоинта.
 *
 * Фильтры едут в адресе карточки: без них родительский журнал перечитал бы параметры как
 * пустые и показал бы под модалом другой список.
 */
import { useLocation, useNavigate, useOutletContext, useParams } from 'react-router';

import { Modal } from '@/components/ui/modal';
import { t } from '@/i18n';
import { PositionCard, type PositionNav } from '@/journal/position-card';
import type { JournalListContext } from '@/routes/journal-page';
import { useIsDesktop } from '@/lib/use-media-query';

function navFrom(
  context: JournalListContext,
  positionId: string | undefined,
  search: string,
): PositionNav {
  const backHref = `/journal${search}`;
  const index = context.items.findIndex((item) => item.id === positionId);
  if (index < 0) {
    return { prev: null, next: null, known: false, backHref };
  }
  const prev = index > 0 ? context.items[index - 1] : undefined;
  const next = context.items[index + 1];
  return {
    prev: prev === undefined ? null : `/journal/${prev.id}${search}`,
    next: next === undefined ? null : `/journal/${next.id}${search}`,
    known: true,
    backHref,
  };
}

export function PositionPage() {
  const { id } = useParams<'id'>();
  const location = useLocation();
  const navigate = useNavigate();
  const isDesktop = useIsDesktop();
  const context = useOutletContext<JournalListContext>();

  const nav = navFrom(context, id, location.search);

  if (id === undefined) {
    return null;
  }

  if (!isDesktop) {
    return <PositionCard positionId={id} nav={nav} />;
  }

  return (
    <Modal
      open
      title={t.pages.position}
      // Прокрутка внутри панели, а не всего окна: карточка выше экрана, а модал
      // выравнивается по центру — при внешней прокрутке её шапка оказывается над
      // верхней границей окна и до неё нельзя добраться вовсе.
      className="max-h-[88vh] max-w-5xl overflow-y-auto"
      onClose={() => {
        void navigate(nav.backHref);
      }}
    >
      <PositionCard positionId={id} nav={nav} headingLevel="h2" />
    </Modal>
  );
}
