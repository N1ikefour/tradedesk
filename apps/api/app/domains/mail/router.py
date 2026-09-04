"""Dev-outbox — SPEC.md 4.

GET /api/v1/dev/outbox -> {items: [...]}

Роутер подключается только при APP_ENV=local (app/main.py): в проде маршрута нет,
и ответ на него — обычный 404. Тело письма содержит код входа, поэтому эндпоинт
не должен существовать нигде, кроме локальной разработки.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.domains.mail.models import DevOutboxEntry

router = APIRouter(prefix="/dev", tags=["dev"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class OutboxEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    to_email: str
    subject: str
    body_text: str
    body_html: str | None
    created_at: datetime


class OutboxResponse(BaseModel):
    """Без курсора: страница показывает последние письма и назад не листает."""

    items: list[OutboxEntry]


@router.get("/outbox", response_model=OutboxResponse)
async def list_outbox(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> OutboxResponse:
    statement = (
        select(DevOutboxEntry)
        # id — uuid7, поэтому вторичная сортировка разводит письма одной миллисекунды.
        .order_by(DevOutboxEntry.created_at.desc(), DevOutboxEntry.id.desc())
        .limit(limit)
    )
    rows = (await session.scalars(statement)).all()
    return OutboxResponse(items=[OutboxEntry.model_validate(row) for row in rows])
