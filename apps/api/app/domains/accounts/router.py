"""Счета — SPEC.md 5.2.

GET    /api/v1/accounts                        -> 200 {items: [Account]}
POST   /api/v1/accounts                        -> 201 Account
PATCH  /api/v1/accounts/{account_id}           -> 200 Account
POST   /api/v1/accounts/{account_id}/pause     -> 200 Account
POST   /api/v1/accounts/{account_id}/resume    -> 200 Account
POST   /api/v1/accounts/{account_id}/archive   -> 200 Account
DELETE /api/v1/accounts/{account_id}           -> 204
POST   /api/v1/accounts/{account_id}/sync-now  -> 202 SyncNow
GET    /api/v1/accounts/{account_id}/sync-runs -> 200 {items: [SyncRun]}

Каждый маршрут с `{account_id}` достаёт счёт через `service.get_owned`: чужой
идентификатор неотличим от несуществующего и даёт `404`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.openapi import domain_errors
from app.domains.accounts import service
from app.domains.accounts.schemas import (
    AccountCreateRequest,
    AccountResponse,
    AccountsResponse,
    AccountUpdateRequest,
    SyncNowResponse,
    SyncRunResponse,
    SyncRunsResponse,
)
from app.domains.auth.dependencies import CurrentUser

router = APIRouter(prefix="/accounts", tags=["accounts"])

# SPEC.md 5.2: «Последние 50 sync_runs». Число фиксировано, курсора у этого списка нет.
SYNC_RUNS_LIMIT = 50

Session = Annotated[AsyncSession, Depends(get_session)]

_NOT_FOUND = {404: [service.ACCOUNT_NOT_FOUND_CODE]}
_ARCHIVED = {422: [service.ACCOUNT_ARCHIVED_CODE]}


@router.get("", response_model=AccountsResponse)
async def list_accounts(
    user: CurrentUser,
    session: Session,
    include_archived: Annotated[
        bool,
        Query(description="Показать и архивные счета. По умолчанию они скрыты"),
    ] = False,
) -> AccountsResponse:
    """Счета пользователя со счётчиком позиций.

    Архивные по умолчанию скрыты: переключатель счетов (SPEC.md 9.2) показывает только
    живые. Экрану «Счета» они нужны — иначе архив исчезает без следа, — поэтому у списка
    есть флаг, а не два разных маршрута.
    """
    rows = await service.list_accounts(session, user.id, include_archived=include_archived)
    return AccountsResponse(
        items=[AccountResponse.from_account(account, count) for account, count in rows]
    )


@router.post(
    "",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
    responses=domain_errors({409: [service.ACCOUNT_EXISTS_CODE]}),
)
async def create_account(
    payload: AccountCreateRequest,
    user: CurrentUser,
    session: Session,
) -> AccountResponse:
    """Создаёт счёт в статусе `pending`. Пароль сразу шифруется и в ответ не попадает."""
    account = await service.create_account(session, user.id, payload)
    # Позиций у нового счёта нет по построению — лишний COUNT не нужен.
    return AccountResponse.from_account(account, 0)


@router.patch(
    "/{account_id}",
    response_model=AccountResponse,
    responses=domain_errors(
        {
            **_NOT_FOUND,
            409: [service.ACCOUNT_EXISTS_CODE],
            422: [service.ACCOUNT_ARCHIVED_CODE, service.NOT_MT5_CODE],
        }
    ),
)
async def update_account(
    account_id: UUID,
    payload: AccountUpdateRequest,
    user: CurrentUser,
    session: Session,
) -> AccountResponse:
    """Частичная правка. Смена пароля или пары сервер+логин возвращает счёт в `pending`."""
    account = await service.get_owned(session, user.id, account_id)
    updated = await service.update_account(session, account, payload)
    return AccountResponse.from_account(updated, await service.positions_count(session, updated.id))


@router.post(
    "/{account_id}/pause",
    response_model=AccountResponse,
    responses=domain_errors({**_NOT_FOUND, **_ARCHIVED}),
)
async def pause_account(account_id: UUID, user: CurrentUser, session: Session) -> AccountResponse:
    account = await service.get_owned(session, user.id, account_id)
    paused = await service.set_paused(session, account, paused=True)
    return AccountResponse.from_account(paused, await service.positions_count(session, paused.id))


@router.post(
    "/{account_id}/resume",
    response_model=AccountResponse,
    responses=domain_errors({**_NOT_FOUND, **_ARCHIVED}),
)
async def resume_account(account_id: UUID, user: CurrentUser, session: Session) -> AccountResponse:
    account = await service.get_owned(session, user.id, account_id)
    resumed = await service.set_paused(session, account, paused=False)
    return AccountResponse.from_account(resumed, await service.positions_count(session, resumed.id))


@router.post(
    "/{account_id}/archive",
    response_model=AccountResponse,
    responses=domain_errors(_NOT_FOUND),
)
async def archive_account(account_id: UUID, user: CurrentUser, session: Session) -> AccountResponse:
    """Выводит счёт из работы и удаляет его credentials. Сделки остаются."""
    account = await service.get_owned(session, user.id, account_id)
    archived = await service.archive_account(session, account)
    return AccountResponse.from_account(
        archived, await service.positions_count(session, archived.id)
    )


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=domain_errors(_NOT_FOUND),
)
async def delete_account(account_id: UUID, user: CurrentUser, session: Session) -> Response:
    """Удаляет счёт со всеми сделками, позициями и записями журнала на них.

    Необратимо; на фронте подтверждается вводом имени счёта (SPEC.md 5.2). Что именно
    теряется — в docstring `service.delete_account`.
    """
    account = await service.get_owned(session, user.id, account_id)
    await service.delete_account(session, account)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{account_id}/sync-now",
    response_model=SyncNowResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=domain_errors(
        {**_NOT_FOUND, 422: [service.ACCOUNT_ARCHIVED_CODE, service.ACCOUNT_PAUSED_CODE]}
    ),
)
async def sync_now(account_id: UUID, user: CurrentUser, session: Session) -> SyncNowResponse:
    """Просит внеочередной синк. `202`, а не `200`: сделки заберёт коллектор, а не этот
    запрос — SPEC.md 8.2, он сверяет `sync_requested_at` с последним синком на очередном
    heartbeat. `collector_online` возвращается затем, чтобы UI отличал «попросили, сейчас
    сделает» от «попросили, но коллектор не запущен».
    """
    account = await service.get_owned(session, user.id, account_id)
    requested_at = await service.request_sync(session, account)
    return SyncNowResponse.accepted(
        account,
        requested_at=requested_at,
        collector_online=service.is_collector_online(account),
    )


@router.get(
    "/{account_id}/sync-runs",
    response_model=SyncRunsResponse,
    responses=domain_errors(_NOT_FOUND),
)
async def list_sync_runs(account_id: UUID, user: CurrentUser, session: Session) -> SyncRunsResponse:
    """Последние 50 прогонов синка, новые сверху."""
    account = await service.get_owned(session, user.id, account_id)
    runs = await service.list_sync_runs(session, account.id, limit=SYNC_RUNS_LIMIT)
    return SyncRunsResponse(items=[SyncRunResponse.from_run(run) for run in runs])
