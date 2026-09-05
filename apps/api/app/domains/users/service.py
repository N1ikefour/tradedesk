"""Правка профиля — SPEC.md 5.7."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth import models
from app.domains.users.schemas import UserUpdateRequest


async def update_profile(
    session: AsyncSession, user: models.User, payload: UserUpdateRequest
) -> models.User:
    """Присваивает только присланные поля. Пользователь — владелец сессии, не параметр.

    Список полей задаёт сама модель запроса: она закрыта `extra="forbid"` и состоит
    ровно из трёх настроек, поэтому `exclude_unset` здесь безопасен — присвоить что-то
    сверх неё нельзя.
    """
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await session.commit()
    return user
