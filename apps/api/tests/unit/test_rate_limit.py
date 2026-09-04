"""Счётчик обращений: поведение при недоступном Redis (S0-04).

Семантика лимита проверяется в `tests/integration/test_rate_limit.py` против настоящего
Redis: решение и инкременты исполняет сам сервер (Lua), и поддельный клиент проверял бы
подделку, а не лимит. Здесь остаётся то, для чего Redis как раз не нужен, — что мёртвый
счётчик закрывает отправку и не тащит в лог URL с паролем.
"""

from __future__ import annotations

from typing import cast

import pytest
from redis.asyncio import Redis

from app.core.rate_limit import RateLimit, RateLimiterUnavailableError, hit_all

RULE = RateLimit(limit=3, window_seconds=600)


class BrokenRedis:
    async def eval(self, script: str, numkeys: int, *args: object) -> object:
        raise ConnectionError("redis://user:hunter2@redis:6379 недоступен")


def _redis(fake: object) -> Redis:
    return cast(Redis, fake)


async def test_empty_counters_do_not_reach_redis() -> None:
    """Вызов без счётчиков не должен падать на мёртвом клиенте — идти туда незачем."""
    assert await hit_all(_redis(BrokenRedis()), []) is None


async def test_unavailable_redis_is_reported_not_swallowed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Молчаливое «разрешено» на мёртвом счётчике снимает лимит целиком — решает вызывающий."""
    from app.core.logging import configure_logging

    configure_logging(secret_values=["hunter2"])

    with pytest.raises(RateLimiterUnavailableError):
        await hit_all(_redis(BrokenRedis()), [("k", RULE)])

    output = capsys.readouterr().out
    assert "rate_limit.unavailable" in output
    # Текст исключения redis-py несёт URL с паролем — в лог идёт только тип.
    assert "hunter2" not in output


async def test_unavailable_redis_does_not_carry_the_url(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Исключение всплывает вверх вместе с `__cause__` — traceback обязан быть чистым."""
    from app.core.logging import configure_logging, get_logger

    configure_logging(secret_values=["hunter2"])
    try:
        await hit_all(_redis(BrokenRedis()), [("k", RULE)])
    except RateLimiterUnavailableError:
        get_logger(__name__).exception("test.rate_limit_failed")

    output = capsys.readouterr().out
    # Контроль проверки: traceback обязан быть в выводе, иначе assert ниже пуст.
    assert "test.rate_limit_failed" in output
    assert "Traceback" in output
    assert "hunter2" not in output
