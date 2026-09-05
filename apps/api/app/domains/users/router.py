"""Профиль пользователя — SPEC.md 5.7.

GET   /api/v1/users/me        -> 200 {id, email, display_name, timezone, day_boundary_hour}
PATCH /api/v1/users/me        -> 200 {id, email, display_name, timezone, day_boundary_hour}
GET   /api/v1/users/timezones -> 200 {items: [...]} | 304

Тот же пользователь, что у `GET /auth/me`, и та же модель ответа `UserResponse`.
Роли разные: `/auth/me` — проба «жива ли сессия», `/users/me` — ресурс профиля.
"""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domains.auth.dependencies import CurrentUser
from app.domains.auth.schemas import UserResponse
from app.domains.users import service
from app.domains.users.schemas import TimezonesResponse, UserUpdateRequest, sorted_timezones

router = APIRouter(prefix="/users", tags=["users"])

# `no-cache` — «храни, но переспрашивай», а не «не храни». max-age здесь был бы вреден:
# устаревшее меню предлагает имя, которое сервер уже не принимает, — ровно та поломка,
# ради которой маршрут и появился. Ревалидация стоит один условный GET и отдаёт 304 без
# девяти килобайт тела. `private`: ответ ходит под сессионной cookie, общим кэшам он не
# принадлежит, даже будучи одинаковым для всех.
TIMEZONES_CACHE_CONTROL = "private, no-cache"

NOT_MODIFIED = 304


@lru_cache(maxsize=1)
def timezones_etag() -> str:
    """Сильный ETag от содержимого: тело — детерминированная функция набора имён.

    Набор меняется только вместе с tzdata образа, то есть с перезапуском процесса, —
    поэтому считается один раз, а не на каждый запрос.
    """
    digest = sha256("\n".join(sorted_timezones()).encode()).hexdigest()
    return f'"{digest[:32]}"'


def _matches_etag(header: str | None, etag: str) -> bool:
    """RFC 9110 §8.8.3: `If-None-Match` может нести список тегов и слабую форму `W/`."""
    if not header:
        return False
    # RFC 9110 §13.1.2: `*` совпадает с любым существующим представлением. Браузеры его в
    # условном GET не шлют, но отвечать телом на «отдай, только если у тебя ничего нет» —
    # нарушение, которое стоит одной ветки.
    if header.strip() == "*":
        return True
    return any(candidate.strip().removeprefix("W/") == etag for candidate in header.split(","))


@router.get("/me", response_model=UserResponse)
async def read_me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdateRequest,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    """Меняет только владельца сессии: чужой идентификатор передать некуда.

    Без сессии тело не разбирается pydantic и состав полей наружу не уходит. Сам JSON
    при этом FastAPI читает раньше зависимостей, поэтому синтаксически битое тело даёт
    400 и без cookie — по нему видно только то, что запрос не JSON.
    """
    updated = await service.update_profile(session, user, payload)
    return UserResponse.model_validate(updated)


@router.get(
    "/timezones",
    response_model=TimezonesResponse,
    responses={NOT_MODIFIED: {"description": "Список не менялся с версии из If-None-Match"}},
)
async def list_timezones(
    request: Request,
    response: Response,
    _user: CurrentUser,
) -> TimezonesResponse | Response:
    """Имена зон, которые принимает `PATCH /users/me`, — из того же набора.

    Под сессией, как и весь `/users`: анонимного потребителя у списка нет, а открытый
    маршрут — это девять килобайт на неаутентифицированный запрос без лимита.
    """
    etag = timezones_etag()
    headers = {"cache-control": TIMEZONES_CACHE_CONTROL, "etag": etag}
    if _matches_etag(request.headers.get("if-none-match"), etag):
        return Response(status_code=NOT_MODIFIED, headers=headers)
    response.headers.update(headers)
    return TimezonesResponse(items=list(sorted_timezones()))
