"""Redis-клиент приложения. Абсолютные импорты: `redis` здесь — пакет из site-packages."""

from __future__ import annotations

import asyncio

from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

PING_TIMEOUT_SECONDS = 2.0


def create_client(settings: Settings) -> Redis:
    return Redis.from_url(
        settings.redis_url.get_secret_value(),
        socket_connect_timeout=PING_TIMEOUT_SECONDS,
        socket_timeout=PING_TIMEOUT_SECONDS,
    )


_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = create_client(get_settings())
    return _client


async def close_redis() -> None:
    """Закрывает пул и сбрасывает синглтон — следующий get_redis() перечитает конфиг."""
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


async def check_redis() -> bool:
    """Проверка живости для /health. Недоступность зависимости — не ошибка приложения."""
    try:
        async with asyncio.timeout(PING_TIMEOUT_SECONDS):
            await get_redis().ping()
    except Exception as exc:
        # В тексте исключения redis-py может оказаться URL с паролем — берём только тип.
        log.warning("health.redis_unavailable", error_type=type(exc).__name__)
        return False
    return True
