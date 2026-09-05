"""Маршруты коллектора — SPEC.md 5.3 и 5.6.

POST /api/v1/ingest/heartbeat                -> 200 {accepted, ignored}
GET  /api/v1/internal/collector/assignments  -> 200 {items}       ⚠️ отдаёт пароль

Авторизация объявлена на роутере, а не на маршрутах: маршрут, забывший зависимость,
открыл бы наружу пароли счетов, и полагаться тут на внимательность нельзя. Любой
будущий маршрут этого файла наследует проверку сам.

Проверка `Origin` (SPEC.md 4) heartbeat'у не мешает: коллектор — не браузер и заголовка
не ставит, а `OriginCheckMiddleware` пропускает запросы без него.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domains.collector import service
from app.domains.collector.dependencies import require_collector_token
from app.domains.collector.schemas import (
    COLLECTOR_ID_MAX_LENGTH,
    AssignmentListResponse,
    AssignmentResponse,
    CollectorId,
    HeartbeatRequest,
    HeartbeatResponse,
)

router = APIRouter(tags=["collector"], dependencies=[Depends(require_collector_token)])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/ingest/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(payload: HeartbeatRequest, session: Session) -> HeartbeatResponse:
    """Коллектор сообщает, что жив и что происходит с каждым его счётом.

    Ответ — счётчики, а не ошибка: heartbeat про десять счетов не должен падать целиком
    из-за одного идентификатора, который коллектор запомнил до архивации счёта.
    """
    result = await service.apply_heartbeat(session, payload)
    return HeartbeatResponse(accepted=result.accepted, ignored=result.ignored)


@router.get("/internal/collector/assignments", response_model=AssignmentListResponse)
async def assignments(
    session: Session,
    collector_id: Annotated[
        CollectorId,
        Query(
            description=(
                "Идентификатор установки коллектора: латиница, цифры и . _ - : @, "
                f"не длиннее {COLLECTOR_ID_MAX_LENGTH} символов"
            )
        ),
    ],
) -> AssignmentListResponse:
    """За какими счетами следить и чем в них входить. **Единственный ответ с паролем.**

    Форма ответа — конверт `{items}`, как у `GET /accounts`. Голый массив нечем расширить,
    а курсорная пагинация из SPEC.md 5.1 потребовала бы ломающей правки вместо добавления
    поля; потребитель (`S1-08`) ещё не написан, поэтому смена формы сейчас стоит ноль.
    SPEC.md 5.6 обновлена тем же диффом.

    `GET`, который пишет: выдача закрепляет `collector_id` за счётом (§5.6). Без этого
    два коллектора в одной сети получили бы одни и те же счета и полезли бы в один
    брокерский аккаунт двумя терминалами.
    """
    issued = await service.issue_assignments(session, collector_id)
    return AssignmentListResponse(
        items=[AssignmentResponse.issued(item.account, item.password) for item in issued]
    )
