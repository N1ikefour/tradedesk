"""Cookie сессии — SPEC.md 4, пункт 3.

`td_session`: HttpOnly; Secure (в prod); SameSite=Lax; Path=/; Max-Age=30d.
Значение — `sessions.id`.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from starlette.responses import Response

from app.core.config import Settings

SESSION_COOKIE_NAME = "td_session"
SESSION_TTL_DAYS = 30
SESSION_MAX_AGE_SECONDS = SESSION_TTL_DAYS * 24 * 60 * 60

# Secure на http://localhost браузер отбрасывает целиком — в local флаг снят.
_SAME_SITE: Literal["lax"] = "lax"


def set_session_cookie(response: Response, settings: Settings, session_id: UUID) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        str(session_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
        httponly=True,
        secure=settings.is_prod,
        samesite=_SAME_SITE,
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    # Атрибуты те же, что при установке: иначе браузер удалит не ту cookie.
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.is_prod,
        samesite=_SAME_SITE,
    )
