"""Auth — SPEC.md 4.

POST /api/v1/auth/request-code -> 202 {status}
POST /api/v1/auth/verify       -> 200 {id, email, display_name, timezone, day_boundary_hour}
POST /api/v1/auth/logout       -> 204
GET  /api/v1/auth/me           -> 200 {id, email, display_name, timezone, day_boundary_hour}
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ip import client_ip, trusted_proxies
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.redis import get_redis
from app.domains.auth import service
from app.domains.auth.cookies import clear_session_cookie, set_session_cookie
from app.domains.auth.dependencies import CurrentUser, session_id_from_request
from app.domains.auth.schemas import (
    RequestCodeRequest,
    RequestCodeResponse,
    UserResponse,
    VerifyRequest,
)
from app.domains.mail.provider import get_email_provider

router = APIRouter(prefix="/auth", tags=["auth"])

# Заголовок клиента: длину режет сервис, здесь только чтение.
USER_AGENT_HEADER = "user-agent"


def _client_ip(request: Request, settings: Settings) -> str | None:
    """Адрес клиента для лимита по IP. X-Forwarded-For — только от доверенного прокси.

    Разбор и обоснование — `app/core/client_ip.py` (X-06).
    """
    return client_ip(request, trusted_proxies(settings))


@router.post(
    "/request-code",
    response_model=RequestCodeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_code(
    payload: RequestCodeRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RequestCodeResponse:
    await service.request_code(
        session=session,
        redis=get_redis(),
        settings=settings,
        provider=get_email_provider(settings, session),
        email=payload.email,
        ip=_client_ip(request, settings),
    )
    return RequestCodeResponse()


@router.post("/verify", response_model=UserResponse)
async def verify(
    payload: VerifyRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    user, row = await service.verify(
        session=session,
        settings=settings,
        email=payload.email,
        code=payload.code,
        user_agent=request.headers.get(USER_AGENT_HEADER),
    )
    set_session_cookie(response, settings, row.id)
    return UserResponse.model_validate(user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def logout(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Идемпотентен: без cookie и с чужим идентификатором ответ тот же 204."""
    session_id = session_id_from_request(request)
    if session_id is not None:
        await service.logout(session, session_id)
    result = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(result, settings)
    return result


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
