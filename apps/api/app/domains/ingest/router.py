"""Маршрут ингеста — SPEC.md 5.3.

POST /api/v1/ingest/deals -> 200 {received, inserted, duplicates, positions_rebuilt, sync_run_id}

Авторизация — тот же сервисный токен коллектора, что у `/ingest/heartbeat` и assignments
(`domains/collector/dependencies.py`). Персональный ключ счёта (`account_ingest_keys`)
контракт называет вторым способом, но он этапа 4 — маршрут о нём пока не знает.

Данные и управление живут в разных доменах намеренно: heartbeat и assignments — это
разговор с процессом коллектора (`domains/collector`), а здесь сделки счёта. Общий у них
только замок на двери.

**Порядок отказов в этом файле — это порядок, в котором отказ становится видимым.**
Пока батч не привязан к счёту, единственный след — лог: `sync_runs.account_id` ссылается
на реальную строку, и вешать прогон некуда. Поэтому счёт ищется первым, а всё, что
отсеяно раньше (401 без токена, 400 на форме тела, 413 на объёме тела), человеку на экране
счёта не видно и видно быть не может. Это цена, а не недосмотр: она названа в
`docs/PROJECT_CONTEXT.md`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.logging import get_logger
from app.core.openapi import domain_errors
from app.core.queue import enqueue
from app.domains.accounts import service as accounts
from app.domains.collector.dependencies import require_collector_token
from app.domains.ingest import service
from app.domains.ingest.schemas import (
    MAX_DEALS_PER_BATCH,
    IngestDealsBatch,
    IngestDealsResponse,
)
from app.worker import REFRESH_DAILY_STATS_NAME

log = get_logger(__name__)

router = APIRouter(tags=["ingest"], dependencies=[Depends(require_collector_token)])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/ingest/deals",
    response_model=IngestDealsResponse,
    responses=domain_errors(
        {
            404: (accounts.ACCOUNT_NOT_FOUND_CODE,),
            422: (accounts.ACCOUNT_ARCHIVED_CODE,),
        }
    ),
)
async def ingest_deals(payload: IngestDealsBatch, session: Session) -> IngestDealsResponse:
    """Батч сделок счёта: вставка, пересборка позиций, отметка в карточке счёта.

    Лимит в 5000 сделок проверяется здесь, а не схемой: pydantic отверг бы такой батч как
    невалидный, то есть `400`, а спека требует `413` — «слишком большой» и «неправильной
    формы» это разные утверждения (разобрано в `schemas.py`).
    """
    started_at = datetime.now(UTC)
    account = await service.load_account(session, payload.account_id)

    if len(payload.deals) > MAX_DEALS_PER_BATCH:
        await _record_refusal(payload, started_at, service.RUN_ERROR_TOO_LARGE)
        raise service.batch_too_large(len(payload.deals))
    if account.status == accounts.STATUS_ARCHIVED:
        await _record_refusal(payload, started_at, service.RUN_ERROR_ARCHIVED)
        raise service.account_archived()

    try:
        result = await service.ingest_batch(session, account, payload, started_at=started_at)
    except Exception:
        # Батч — одна транзакция: откат целиком, а отказ записывается своей (см. service).
        await session.rollback()
        await _record_refusal(payload, started_at, service.RUN_ERROR_INTERNAL)
        raise

    # После коммита: пересчитывать кэш по сделкам, которых может не оказаться в базе,
    # незачем. Неудача постановки задачи ответ не роняет — см. `core/queue.py`.
    #
    # Нет новых сделок — нечему было измениться: `positions` производны от `deals`, а
    # снимок открытой позиции влияет только на `status` (`S1-03`). Иначе задача уезжала бы
    # в очередь на каждом тике синка: коллектор перезапрашивает сутки каждые 60 секунд.
    #
    # Уходит **отрезок времени** тронутых сделок, а не список дней: день режется по зоне и
    # границе дня владельца счёта (`docs/metrics.md` §6), а ингест владельца не знает — он
    # видит счёт. Дни внутри отрезка считает сама `refresh_daily_stats`, и правило
    # торгового дня остаётся в одном месте.
    if result.inserted and result.touched is not None:
        first, last = result.touched
        await enqueue(
            REFRESH_DAILY_STATS_NAME,
            str(account.id),
            within=[first.isoformat(), last.isoformat()],
        )

    return IngestDealsResponse(
        received=result.received,
        inserted=result.inserted,
        duplicates=result.duplicates,
        positions_rebuilt=result.positions_rebuilt,
        sync_run_id=result.sync_run_id,
    )


async def _record_refusal(payload: IngestDealsBatch, started_at: datetime, error: str) -> None:
    """Отказ по счёту, который уже найден, — строка `sync_runs`, видимая на экране (`S1-11`)."""
    await service.record_failed_run(
        payload.account_id,
        payload.source,
        started_at=started_at,
        received=len(payload.deals),
        offset_minutes=payload.server_utc_offset_minutes,
        error=error,
    )
