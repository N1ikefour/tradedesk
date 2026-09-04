"""Зависимость «текущий пользователь»: сессия из cookie (SPEC.md 4)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.domains.auth import models, service
from app.domains.auth.cookies import SESSION_COOKIE_NAME, set_session_cookie


def session_id_from_request(request: Request) -> UUID | None:
    """Значение cookie — `sessions.id`. Мусор в cookie равнозначен её отсутствию."""
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


async def current_user(
    response: Response,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> models.User:
    session_id = session_id_from_request(request)
    if session_id is None:
        raise service.unauthorized()
    loaded = await service.load_session(session, session_id)
    if loaded is None:
        raise service.unauthorized()
    row, user = loaded
    if await service.touch_session(session, row):
        # Cookie переставляется вместе с продлением в БД: иначе браузер выбросит её
        # через 30 дней после входа, сколько бы раз пользователь ни заходил.
        set_session_cookie(response, settings, row.id)
    return user


CurrentUser = Annotated[models.User, Depends(current_user)]
