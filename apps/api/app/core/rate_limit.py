"""Счётчик обращений в Redis: фиксированное окно на ключ (SPEC.md 4)."""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class RateLimit:
    """`limit` обращений за `window_seconds`."""

    limit: int
    window_seconds: int


class RateLimiterUnavailableError(RuntimeError):
    """Счётчик не отвечает, обращение не учтено.

    Что делать дальше — решает вызывающий: пропустить обращение можно только там, где
    отсутствие лимита ничего не открывает. Молча возвращать «разрешено» здесь нельзя.
    """


async def peek(redis: Redis, key: str, rule: RateLimit) -> int | None:
    """Проверяет лимит, НЕ трогая счётчик. Возвращает `retry_after`, если лимит исчерпан.

    Отдельная от `hit` проверка нужна там, где счётчиков несколько: инкремент до решения
    означает, что запрос, отбитый одним лимитом, платит по всем остальным. Вызывающий
    сначала опрашивает все счётчики через `peek` и платит `hit` только за пропущенный
    запрос (X-06).

    Пара `peek` + `hit` не атомарна: несколько одновременных запросов могут пройти проверку
    до инкремента и превысить лимит на их число. Это осознанный размен. Атомарный `hit`
    первым списывает квоту с отбитых запросов, и один нетерпеливый пользователь блокирует
    часовой лимит по адресу для всех остальных; лишнее письмо в редкой гонке дешевле.
    """
    try:
        raw = await redis.get(key)
        count = int(raw) if raw is not None else 0
        if count < rule.limit:
            return None
        ttl = int(await redis.ttl(key))
    except Exception as exc:
        # Текст исключения redis-py может содержать URL с паролем — берём только тип.
        log.warning("rate_limit.unavailable", error_type=type(exc).__name__)
        raise RateLimiterUnavailableError(key) from exc
    return max(ttl, 1)


async def hit(redis: Redis, key: str, rule: RateLimit) -> int | None:
    """Регистрирует обращение. Возвращает `retry_after` в секундах, если лимит исчерпан.

    Окно фиксированное: TTL ставится на первом обращении и не продлевается — иначе
    поток запросов удерживал бы клиента в блокировке бесконечно.
    """
    try:
        count = int(await redis.incr(key))
        ttl = int(await redis.ttl(key))
        if ttl < 0:
            # Ключ без TTL: первое обращение либо гонка двух первых. Окно ставим здесь.
            await redis.expire(key, rule.window_seconds)
            ttl = rule.window_seconds
    except Exception as exc:
        # Текст исключения redis-py может содержать URL с паролем — берём только тип.
        log.warning("rate_limit.unavailable", error_type=type(exc).__name__)
        raise RateLimiterUnavailableError(key) from exc
    if count > rule.limit:
        return max(ttl, 1)
    return None
