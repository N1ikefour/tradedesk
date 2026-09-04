"""Счётчик обращений в Redis: фиксированное окно на ключ (SPEC.md 4).

Решение и оба инкремента — одна серверная операция. Иначе никак: между «прочитать
счётчик» и «увеличить счётчик» из питона стоят два await-а, и на них проходит весь
бёрст целиком. Прогон ревью S0-06 с 60 предоткрытых сокетов по барьеру при лимите
3 за 10 минут: прошли **60 из 60**, то есть лимита не было вовсе — ни почтового,
ни того, ради которого затевался X-06. Последовательный прогон и `xargs -P` этого
не показывают: процессы стартуют вразнобой.

Требований два, и они выполняются только вместе:

* **атомарность** — при любой конкуренции пропущено не больше `limit` обращений;
* **отбитый запрос не платит** — если хоть один счётчик исчерпан, не увеличивается
  ни один. Иначе запрос, отбитый общим лимитом по IP, дополнительно выжигает личную
  квоту пользователя, а нетерпеливый пользователь, десять раз нажавший «прислать код»
  на свой адрес, выбирает часовой бюджет установки соседям (X-06).
"""

from __future__ import annotations

from collections.abc import Sequence
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


# Redis исполняет скрипт целиком, не прерываясь на другие команды, — отсюда и атомарность
# «проверить всё, увеличить всё или не трогать ничего». Ни один клиент не видит состояния
# посередине, и окна, в котором чужой счётчик уже увеличен, не существует.
#
# KEYS — счётчики; ARGV — пары (limit, window) в том же порядке.
# Ответ: {индекс исчерпанного счётчика или 0, retry_after в секундах}.
_HIT_ALL_SCRIPT = """
for i = 1, #KEYS do
  local limit = tonumber(ARGV[i * 2 - 1])
  local count = tonumber(redis.call('GET', KEYS[i]) or '0')
  if count >= limit then
    local ttl = redis.call('TTL', KEYS[i])
    if ttl < 0 then ttl = tonumber(ARGV[i * 2]) end
    if ttl < 1 then ttl = 1 end
    return {i, ttl}
  end
end
for i = 1, #KEYS do
  redis.call('INCR', KEYS[i])
  -- Окно фиксированное: TTL ставится на первом обращении и не продлевается, иначе поток
  -- запросов удерживал бы клиента в блокировке бесконечно. Проверяем TTL, а не значение
  -- счётчика: ключ без TTL остаётся и после сбоя ровно на этом месте.
  if redis.call('TTL', KEYS[i]) < 0 then
    redis.call('EXPIRE', KEYS[i], tonumber(ARGV[i * 2]))
  end
end
return {0, 0}
"""


async def hit_all(redis: Redis, counters: Sequence[tuple[str, RateLimit]]) -> int | None:
    """Регистрирует обращение сразу по всем счётчикам. `retry_after`, если хоть один исчерпан.

    Всё или ничего: при исчерпанном счётчике не увеличивается ни один, включая те, что
    были под лимитом. Возвращается `retry_after` первого исчерпанного — порядок задаёт
    вызывающий, и осмысленно ставить первым самое длинное окно, чтобы ответ не обещал
    клиенту меньше, чем ему на самом деле ждать.
    """
    if not counters:
        return None
    keys = [key for key, _ in counters]
    # ARGV уходит строками — Redis всё равно передаёт аргументы скрипта как строки,
    # а Lua поднимает их обратно через tonumber.
    args: list[str] = []
    for _, rule in counters:
        args += [str(rule.limit), str(rule.window_seconds)]
    try:
        # eval, а не register_script: EVALSHA экономит несколько сотен байт на запрос
        # ценой ветки «скрипт выпал из кэша Redis». Экономия на выпуске кода входа
        # не стоит второго пути исполнения.
        blocked_index, retry_after = await redis.eval(  # type: ignore[misc]
            _HIT_ALL_SCRIPT, len(keys), *keys, *args
        )
    except Exception as exc:
        # Текст исключения redis-py может содержать URL с паролем — берём только тип.
        log.warning("rate_limit.unavailable", error_type=type(exc).__name__)
        raise RateLimiterUnavailableError(",".join(keys)) from exc
    if int(blocked_index) == 0:
        return None
    return max(int(retry_after), 1)
