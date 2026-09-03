"""Служебные эндпоинты — SPEC.md 5.7.

GET /api/v1/health  -> {status, db, redis, version}
GET /api/v1/version -> {version}
"""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.db import check_database
from app.core.redis import check_redis

router = APIRouter(tags=["system"])

DependencyStatus = Literal["ok", "unavailable"]


class HealthResponse(BaseModel):
    # degraded: приложение живо, но зависимость недоступна. HTTP-код при этом 200 —
    # падение Postgres не делает сам сервис неработоспособным для мониторинга.
    status: Literal["ok", "degraded"]
    db: DependencyStatus
    redis: DependencyStatus
    version: str


class VersionResponse(BaseModel):
    version: str


def _status(is_alive: bool) -> DependencyStatus:
    return "ok" if is_alive else "unavailable"


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    # Обе проверки параллельно: недоступная зависимость ждёт таймаут, а их два.
    db_alive, redis_alive = await asyncio.gather(check_database(), check_redis())
    return HealthResponse(
        status="ok" if db_alive and redis_alive else "degraded",
        db=_status(db_alive),
        redis=_status(redis_alive),
        version=__version__,
    )


@router.get("/version", response_model=VersionResponse)
async def get_version() -> VersionResponse:
    return VersionResponse(version=__version__)
