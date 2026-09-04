"""Счётчик обращений: фиксированное окно и поведение при недоступном Redis (S0-04)."""

from __future__ import annotations

from typing import cast

import pytest
from redis.asyncio import Redis

from app.core.rate_limit import RateLimit, RateLimiterUnavailableError, hit

RULE = RateLimit(limit=3, window_seconds=600)


class FakeRedis:
    """Минимальный INCR/TTL/EXPIRE. Настоящий Redis проверяется в integration-тестах."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.expire_calls = 0

    async def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)

    async def expire(self, key: str, seconds: int) -> bool:
        self.expire_calls += 1
        self.ttls[key] = seconds
        return True


class BrokenRedis:
    async def incr(self, key: str) -> int:
        raise ConnectionError("redis://user:hunter2@redis:6379 недоступен")


def _redis(fake: object) -> Redis:
    return cast(Redis, fake)


async def test_allows_until_limit_reached() -> None:
    fake = FakeRedis()

    results = [await hit(_redis(fake), "k", RULE) for _ in range(3)]

    assert results == [None, None, None]


async def test_blocks_after_limit_and_reports_retry_after() -> None:
    fake = FakeRedis()
    for _ in range(3):
        await hit(_redis(fake), "k", RULE)

    retry_after = await hit(_redis(fake), "k", RULE)

    assert retry_after == RULE.window_seconds


async def test_window_is_not_extended_by_further_hits() -> None:
    """Фиксированное окно: TTL ставится один раз, иначе поток запросов держал бы блок вечно."""
    fake = FakeRedis()
    for _ in range(3):
        await hit(_redis(fake), "k", RULE)
    fake.ttls["k"] = 42

    retry_after = await hit(_redis(fake), "k", RULE)

    assert retry_after == 42
    assert fake.expire_calls == 1


async def test_keys_are_counted_independently() -> None:
    fake = FakeRedis()
    for _ in range(3):
        await hit(_redis(fake), "a", RULE)

    assert await hit(_redis(fake), "b", RULE) is None
    assert await hit(_redis(fake), "a", RULE) is not None


async def test_unavailable_redis_is_reported_not_swallowed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Молчаливое «разрешено» на мёртвом счётчике снимает лимит целиком — решает вызывающий."""
    from app.core.logging import configure_logging

    configure_logging(secret_values=["hunter2"])

    with pytest.raises(RateLimiterUnavailableError):
        await hit(_redis(BrokenRedis()), "k", RULE)

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
        await hit(_redis(BrokenRedis()), "k", RULE)
    except RateLimiterUnavailableError:
        get_logger(__name__).exception("test.rate_limit_failed")

    output = capsys.readouterr().out
    # Контроль проверки: traceback обязан быть в выводе, иначе assert ниже пуст.
    assert "test.rate_limit_failed" in output
    assert "Traceback" in output
    assert "hunter2" not in output
