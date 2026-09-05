"""Профиль пользователя — SPEC.md 5.7.

GET   /api/v1/users/me -> 200 {id, email, display_name, timezone, day_boundary_hour}
PATCH /api/v1/users/me -> 200 {id, email, display_name, timezone, day_boundary_hour}

Тот же пользователь, что у `GET /auth/me`, и та же модель ответа `UserResponse`.
Роли разные: `/auth/me` — проба «жива ли сессия», `/users/me` — ресурс профиля.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domains.auth.dependencies import CurrentUser
from app.domains.auth.schemas import UserResponse
from app.domains.users import service
from app.domains.users.schemas import UserUpdateRequest

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def read_me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdateRequest,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserResponse:
    """Меняет только владельца сессии: чужой идентификатор передать некуда."""
    updated = await service.update_profile(session, user, payload)
    return UserResponse.model_validate(updated)
