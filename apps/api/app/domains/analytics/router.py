"""Аналитика — SPEC.md 5.5 и 5.4.

GET /api/v1/analytics/summary  -> 200 SummaryResponse
GET /api/v1/journal/calendar   -> 200 CalendarResponse

Календарь оставлен на своём пути из SPEC.md 5.4 (`/journal/calendar`), но живёт в этом
роутере, а не в журнале: считает он то же самое, что и сводка, теми же правилами дня и
периода. Путь — контракт для фронта, домен — место, где чинят формулу; разводить их по
разным файлам ради совпадения слова в URL значило бы держать одно правило в двух местах.

Оба маршрута скоупятся по владельцу через `journal.service.resolve_account_ids`: чужой
`account_id` в фильтре — `404 account_not_found`, как и в списке журнала, а не пустая
сводка. Пустой фильтр — все неархивированные счета пользователя (SPEC.md 5.1).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.openapi import domain_errors
from app.core.query import reject_repeated_query_params
from app.domains.accounts import service as accounts_service
from app.domains.analytics import service
from app.domains.analytics.schemas import (
    CalendarDay,
    CalendarQuery,
    CalendarResponse,
    SummaryQuery,
    SummaryResponse,
)
from app.domains.auth.dependencies import CurrentUser

router = APIRouter(tags=["analytics"])

Session = Annotated[AsyncSession, Depends(get_session)]

_ACCOUNT_NOT_FOUND = {404: [accounts_service.ACCOUNT_NOT_FOUND_CODE]}


@router.get(
    "/analytics/summary",
    response_model=SummaryResponse,
    responses=domain_errors(_ACCOUNT_NOT_FOUND),
    # Зависимость, а не проверка в теле: она обязана отработать до того, как FastAPI
    # схлопнет повторённый параметр в одно значение (разбор — в `core/query.py`).
    dependencies=[Depends(reject_repeated_query_params)],
)
async def read_summary(
    user: CurrentUser, session: Session, filters: Annotated[SummaryQuery, Query()]
) -> SummaryResponse:
    """Сводка за период — шапка журнала и дашборд.

    Считаются **закрытые** позиции: у открытой в `net_pnl` лежат накопленные издержки, а
    не результат. Открытые видны отдельным счётчиком `open_positions`, и он же объясняет
    разницу между этой суммой и суммой колонки в списке (`docs/metrics.md` §1.1).
    """
    summary = await service.summary(
        session, user.id, filters.account_id_list, filters.date_from, filters.date_to
    )
    return SummaryResponse.from_summary(summary)


@router.get(
    "/journal/calendar",
    response_model=CalendarResponse,
    responses=domain_errors(_ACCOUNT_NOT_FOUND),
    dependencies=[Depends(reject_repeated_query_params)],
)
async def read_calendar(
    user: CurrentUser, session: Session, filters: Annotated[CalendarQuery, Query()]
) -> CalendarResponse:
    """Дни месяца в зоне пользователя — SPEC.md 5.4.

    Границы каждого дня приходят готовыми: их и надо подставлять в `?from=&to=` журнала,
    чтобы список за день совпал с днём календаря. Пересчитывать день на клиенте не нужно
    (`docs/metrics.md` §2.2).
    """
    year, month = filters.year_month
    days = await service.calendar(
        session,
        user.id,
        filters.account_id_list,
        year,
        month,
        user.timezone,
        user.day_boundary_hour,
    )
    return CalendarResponse(
        month=filters.month,
        timezone=user.timezone,
        day_boundary_hour=user.day_boundary_hour,
        days=[CalendarDay.from_day(day) for day in days],
    )
