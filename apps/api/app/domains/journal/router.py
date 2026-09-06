"""Журнал — SPEC.md 5.4.

GET /api/v1/journal/positions        -> 200 {items: [PositionListItem], next_cursor}
GET /api/v1/journal/positions/{id}   -> 200 PositionCard

Только два маршрута: правки записи и рефлексии — `S2-02`, ручные сделки — `S2-03`,
вложения — `S2-04`.

Оба скоупятся по владельцу: список — через `service.resolve_account_ids`, карточка —
соединением с `trading_accounts` по `user_id`. Чужой идентификатор неотличим от
несуществующего и в обоих случаях даёт `404`.

Испорченный курсор своего кода не получает: он разбирается на границе, в
`PositionsQuery`, и уходит обычным `400 validation_error` с `details.fields`
(разбор — в шапке `cursor.py`). Повторённый параметр — тоже `400`, а не молча выборка по
последнему из значений (`core/query.py`).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.openapi import domain_errors
from app.core.query import reject_repeated_query_params
from app.domains.accounts import service as accounts_service
from app.domains.auth.dependencies import CurrentUser
from app.domains.journal import service
from app.domains.journal.schemas import (
    PositionCard,
    PositionListItem,
    PositionsPage,
    PositionsQuery,
)

router = APIRouter(prefix="/journal", tags=["journal"])

Session = Annotated[AsyncSession, Depends(get_session)]
Filters = Annotated[PositionsQuery, Query()]


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
    responses=domain_errors({404: [service.POSITION_NOT_FOUND_CODE]}),
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
