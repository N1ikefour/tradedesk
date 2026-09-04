"""Счётчик обращений против настоящего Redis — X-06.

Решение и инкременты исполняет сам Redis (Lua), поэтому подделка клиента здесь проверяла
бы подделку, а не лимит. Отсюда integration, а не unit.

⚠️ Конкурентный тест в этом файле — не украшение. Реализация «прочитать счётчик, потом
увеличить» проходит все последовательные проверки и при этом пропускает бёрст целиком:
между чтением и инкрементом стоят два await-а. Ревью S0-06 положило 60 из 60 запросов
при лимите 3. Последовательный прогон и `xargs -P` этого не видят.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from redis.asyncio import Redis
from testcontainers.community.redis import RedisContainer

from app.core.rate_limit import RateLimit, RateLimiterUnavailableError, hit_all

pytestmark = pytest.mark.integration

# Числа из SPEC.md 4: три запроса на адрес почты за 10 минут, десять на IP за час.
EMAIL_RULE = RateLimit(limit=3, window_seconds=10 * 60)
IP_RULE = RateLimit(limit=10, window_seconds=60 * 60)

EMAIL_KEY = "rl:test:email"
IP_KEY = "rl:test:ip"

# Столько одновременных обращений подавало ревью. Меньше десятка гонку не показывает.
BURST = 60


@pytest.fixture(scope="module")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture
async def redis(redis_container: RedisContainer) -> AsyncIterator[Redis]:
    url = (
        f"redis://{redis_container.get_container_host_ip()}:"
        f"{redis_container.get_exposed_port(6379)}/0"
    )
    client = Redis.from_url(url)
    await client.flushdb()
    yield client
    await client.aclose()


async def counter(redis: Redis, key: str) -> int:
    raw = await redis.get(key)
    return int(raw) if raw is not None else 0


async def test_allows_until_limit_reached(redis: Redis) -> None:
    results = [await hit_all(redis, [(EMAIL_KEY, EMAIL_RULE)]) for _ in range(EMAIL_RULE.limit)]

    assert results == [None] * EMAIL_RULE.limit
    assert await counter(redis, EMAIL_KEY) == EMAIL_RULE.limit


async def test_blocks_after_limit_and_reports_retry_after(redis: Redis) -> None:
    for _ in range(EMAIL_RULE.limit):
        await hit_all(redis, [(EMAIL_KEY, EMAIL_RULE)])

    retry_after = await hit_all(redis, [(EMAIL_KEY, EMAIL_RULE)])

    assert retry_after is not None
    assert 0 < retry_after <= EMAIL_RULE.window_seconds


async def test_window_is_not_extended_by_further_hits(redis: Redis) -> None:
    """Фиксированное окно: TTL ставится один раз, иначе поток запросов держал бы блок вечно."""
    for _ in range(EMAIL_RULE.limit):
        await hit_all(redis, [(EMAIL_KEY, EMAIL_RULE)])
    await redis.expire(EMAIL_KEY, 42)

    retry_after = await hit_all(redis, [(EMAIL_KEY, EMAIL_RULE)])

    assert retry_after == 42
    assert await redis.ttl(EMAIL_KEY) <= 42


async def test_keys_are_counted_independently(redis: Redis) -> None:
    for _ in range(EMAIL_RULE.limit):
        await hit_all(redis, [("rl:test:a", EMAIL_RULE)])

    assert await hit_all(redis, [("rl:test:b", EMAIL_RULE)]) is None
    assert await hit_all(redis, [("rl:test:a", EMAIL_RULE)]) is not None


async def test_blocked_request_pays_nothing(redis: Redis) -> None:
    """Всё или ничего: исчерпанный счётчик не даёт списать и с того, что был под лимитом.

    Без этого запрос, отбитый общим лимитом по IP, выжигал бы личную квоту пользователя,
    а нетерпеливый пользователь — часовой бюджет установки (X-06).
    """
    counters = [(IP_KEY, IP_RULE), (EMAIL_KEY, EMAIL_RULE)]
    for _ in range(EMAIL_RULE.limit):
        assert await hit_all(redis, counters) is None
    spent_ip = await counter(redis, IP_KEY)

    for _ in range(20):
        assert await hit_all(redis, counters) is not None

    assert await counter(redis, IP_KEY) == spent_ip
    assert await counter(redis, EMAIL_KEY) == EMAIL_RULE.limit


async def test_retry_after_names_the_first_exhausted_counter(redis: Redis) -> None:
    """Порядок задаёт вызывающий: первым идёт более длинное окно, чтобы ответ не врал."""
    await redis.set(IP_KEY, IP_RULE.limit, ex=IP_RULE.window_seconds)
    await redis.set(EMAIL_KEY, EMAIL_RULE.limit, ex=EMAIL_RULE.window_seconds)

    retry_after = await hit_all(redis, [(IP_KEY, IP_RULE), (EMAIL_KEY, EMAIL_RULE)])

    assert retry_after is not None
    assert retry_after > EMAIL_RULE.window_seconds


async def test_concurrent_burst_cannot_outrun_the_limit(redis: Redis) -> None:
    """⚠️ Тест, который ловит неатомарную реализацию. Барьер обязателен.

    Соединения открываются заранее, все корутины отпускаются одновременно. Реализация
    «peek, потом hit» пропускает здесь почти весь бёрст (57 из 60 в прогоне ревью);
    атомарный скрипт держит границу при любой конкуренции.
    """
    counters = [(IP_KEY, IP_RULE), (EMAIL_KEY, EMAIL_RULE)]
    # Прогрев пула: установка соединения иначе разносит корутины по времени и прячет гонку.
    await asyncio.gather(*(redis.ping() for _ in range(BURST)))
    barrier = asyncio.Barrier(BURST)

    async def attempt() -> int | None:
        await barrier.wait()
        return await hit_all(redis, counters)

    results = await asyncio.gather(*(attempt() for _ in range(BURST)))

    allowed = [result for result in results if result is None]
    assert len(allowed) == EMAIL_RULE.limit, f"пропущено {len(allowed)} из {BURST}"
    assert await counter(redis, EMAIL_KEY) == EMAIL_RULE.limit
    assert await counter(redis, IP_KEY) == EMAIL_RULE.limit


async def test_unavailable_redis_closes_the_gate(redis_container: RedisContainer) -> None:
    """Fail-closed остаётся: мёртвый счётчик не должен превращаться в «разрешено»."""
    dead = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=1)

    with pytest.raises(RateLimiterUnavailableError):
        await hit_all(dead, [(EMAIL_KEY, EMAIL_RULE)])

    await dead.aclose()
