"""Журнал — SPEC.md 5.4.

GET    /api/v1/journal/positions                  -> 200 {items: [PositionListItem], next_cursor}
GET    /api/v1/journal/positions/{id}             -> 200 PositionCard
PUT    /api/v1/journal/positions/{id}/entry       -> 200 JournalEntryDetail
PUT    /api/v1/journal/positions/{id}/reflection  -> 200 ReflectionDetail
GET    /api/v1/journal/tags                       -> 200 {items: [TagResponse]}
POST   /api/v1/journal/tags                       -> 200 TagResponse
DELETE /api/v1/journal/tags/{tag_id}              -> 200 TagDeletedResponse
GET    /api/v1/journal/vocab                      -> 200 VocabResponse

Ручные сделки — `S2-03`, вложения — `S2-04`, календарь — `S2-05`.

⚠️ **Оба `PUT` заменяют запись целиком, и потому требуют все поля.** Тело без поля — это
`400 validation_error`, а не «оставь как было»: автосохранение карточки (`S2-07`) с
частичным телом иначе стирало бы заметку молча. Разбор — в шапке `schemas.py`.

Каждый маршрут скоупится по владельцу: список — через `service.resolve_account_ids`,
карточка и записи — соединением с `trading_accounts` по `user_id`, теги — колонкой
`tags.user_id`. Чужой идентификатор неотличим от несуществующего и всюду даёт `404`.

Испорченный курсор своего кода не получает: он разбирается на границе, в
`PositionsQuery`, и уходит обычным `400 validation_error` с `details.fields`
(разбор — в шапке `cursor.py`). Повторённый параметр — тоже `400`, а не молча выборка по
последнему из значений (`core/query.py`).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.openapi import domain_errors
from app.core.query import reject_repeated_query_params
from app.domains.accounts import service as accounts_service
from app.domains.auth.dependencies import CurrentUser
from app.domains.journal import service
from app.domains.journal.schemas import (
    JournalEntryDetail,
    JournalEntryUpdate,
    PositionCard,
    PositionListItem,
    PositionsPage,
    PositionsQuery,
    ReflectionDetail,
    ReflectionUpdate,
    TagCreateRequest,
    TagDeletedResponse,
    TagResponse,
    TagsResponse,
    VocabResponse,
)

router = APIRouter(prefix="/journal", tags=["journal"])

Session = Annotated[AsyncSession, Depends(get_session)]
Filters = Annotated[PositionsQuery, Query()]

_POSITION_NOT_FOUND = {404: [service.POSITION_NOT_FOUND_CODE]}

# Словари SPEC.md 3.5 меняются только вместе с образом, но устаревшая копия у клиента
# опаснее лишнего запроса: по ней фронт нарисует меню без значения, которое сервер уже
# принимает, и оставит без подписи ключ, который уже сохранён в чужой рефлексии.
# `no-cache` — «храни, но каждый раз переспрашивай», это и требуется.
#
# ETag, как у `/users/timezones`, здесь намеренно **нет**. Там он снимает девять
# килобайт имён зон с каждой ревалидации, здесь тело — четыре коротких списка, и `304`
# экономил бы меньше, чем стоят собственная реализация условного GET во втором домене и
# расхождение с первой. Появится причина (словари станут пользовательскими) — общий
# разбор `If-None-Match` переедет в `core/` и будет один на оба маршрута.
VOCAB_CACHE_CONTROL = "private, no-cache"


@router.get(
    "/positions",
    response_model=PositionsPage,
    responses=domain_errors({404: [accounts_service.ACCOUNT_NOT_FOUND_CODE]}),
    # Зависимость, а не проверка в теле: она обязана отработать до того, как FastAPI
    # схлопнет повторённый параметр в одно значение (разбор — в `core/query.py`).
    dependencies=[Depends(reject_repeated_query_params)],
)
async def list_positions(user: CurrentUser, session: Session, filters: Filters) -> PositionsPage:
    """Страница журнала.

    Сортировка по умолчанию — `close_time:desc`: журнал открывают, чтобы увидеть, чем
    кончился сегодняшний день. Открытые позиции при сортировке по времени закрытия и по
    длительности идут первой группой в обе стороны — у них этих значений нет, а прятать
    их в хвост тысячестрочного списка нельзя.
    """
    rows, counts, next_cursor = await service.list_positions(session, user.id, filters)
    return PositionsPage(
        items=[
            PositionListItem.from_row(
                row.position,
                row.account,
                row.entry,
                row.reflection,
                counts.get(row.position.id, 0),
            )
            for row in rows
        ],
        next_cursor=next_cursor,
    )


@router.get(
    "/positions/{position_id}",
    response_model=PositionCard,
    responses=domain_errors(_POSITION_NOT_FOUND),
)
async def get_position(position_id: UUID, user: CurrentUser, session: Session) -> PositionCard:
    """Карточка позиции со сделками, записью журнала и рефлексией."""
    row = await service.get_position(session, user.id, position_id)
    deals = await service.position_deals(session, row.position)
    counts = await service.attachment_counts(session, [row.position.id])
    return PositionCard.from_row(
        row.position,
        row.account,
        row.entry,
        row.reflection,
        counts.get(row.position.id, 0),
        deals,
    )


@router.put(
    "/positions/{position_id}/entry",
    response_model=JournalEntryDetail,
    responses=domain_errors(_POSITION_NOT_FOUND),
)
async def save_entry(
    position_id: UUID, payload: JournalEntryUpdate, user: CurrentUser, session: Session
) -> JournalEntryDetail:
    """Заметки, теги, план и риск — полной заменой.

    ⚠️ Тело обязано нести **все** поля модели: `PUT` из SPEC.md 5.4 заменяет запись
    целиком, и отсутствие поля означало бы «сотри его». Пропущенное поле — `400`, а не
    молчаливая потеря; очистка выражается явным `null` (у `tags` — пустым массивом).

    В ответе теги приходят в написании словаря, которое может отличаться от присланного
    регистром: `trend` при заведённом `Trend` сохранится как `Trend` (`service.resolve_tags`).
    Незнакомый тег заводится в словаре сам, без цвета, поэтому появление в ответе тега,
    которого нет в загруженном списке, — повод перечитать `GET /journal/tags`.
    """
    entry = await service.save_entry(session, user.id, position_id, payload)
    return JournalEntryDetail.from_entry(entry)


@router.put(
    "/positions/{position_id}/reflection",
    response_model=ReflectionDetail,
    responses=domain_errors(_POSITION_NOT_FOUND),
)
async def save_reflection(
    position_id: UUID, payload: ReflectionUpdate, user: CurrentUser, session: Session
) -> ReflectionDetail:
    """Рефлексия — полной заменой, с теми же правилами обязательности полей, что у entry.

    `filled_at` считает сервер: он ставится первым сохранением, в котором есть хоть одно
    заполненное поле, не переставляется последующими правками и снимается, если рефлексию
    очистили целиком. Что считается заполненным — `ReflectionUpdate.is_filled`.
    """
    reflection = await service.save_reflection(session, user.id, position_id, payload)
    return ReflectionDetail.from_reflection(reflection)


@router.get("/tags", response_model=TagsResponse)
async def list_tags(user: CurrentUser, session: Session) -> TagsResponse:
    """Словарь тегов пользователя со счётчиком позиций у каждого.

    Счётчик — то, что показывают в подтверждении удаления: тег снимается со всех позиций,
    и это единственный способ узнать масштаб до, а не после.
    """
    rows = await service.list_tags(session, user.id)
    return TagsResponse(items=[TagResponse.from_tag(tag, count) for tag, count in rows])


@router.post("/tags", response_model=TagResponse)
async def create_tag(payload: TagCreateRequest, user: CurrentUser, session: Session) -> TagResponse:
    """Заводит тег или задаёт существующему написание и цвет.

    ⚠️ Не `201`, и это не оплошность: маршрут не только создаёт. Тег с таким же именем
    без учёта регистра — не конфликт, а он же самый, и запрос задаёт ему присланное
    написание и цвет, переписывая тег на всех позициях пользователя. Это единственное
    место, где написание тега меняется: `PUT entry` только пользуется словарём и ничего
    в нём не переименовывает.
    """
    tag, usage = await service.upsert_tag(session, user.id, payload.name, payload.color)
    return TagResponse.from_tag(tag, usage)


@router.delete(
    "/tags/{tag_id}",
    response_model=TagDeletedResponse,
    responses=domain_errors({404: [service.TAG_NOT_FOUND_CODE]}),
)
async def delete_tag(tag_id: UUID, user: CurrentUser, session: Session) -> TagDeletedResponse:
    """Удаляет тег из словаря и снимает его со всех позиций пользователя.

    ⚠️ Не `204`: изменились не только словарь, но и позиции, и сколько их было — клиенту
    после факта взять неоткуда. Чужой тег неотличим от несуществующего, оба — `404`.
    """
    name, updated = await service.delete_tag(session, user.id, tag_id)
    return TagDeletedResponse(name=name, positions_updated=updated)


@router.get("/vocab", response_model=VocabResponse)
async def read_vocab(response: Response, _user: CurrentUser) -> VocabResponse:
    """Словари эмоций, ошибок и оценок — SPEC.md 3.5.

    Под сессией, как и `/users/timezones`: анонимного потребителя у словаря нет.
    Заголовок кэширования — единственная защита от устаревшей копии, см. `VOCAB_CACHE_CONTROL`.
    """
    response.headers["cache-control"] = VOCAB_CACHE_CONTROL
    return VocabResponse.current()
