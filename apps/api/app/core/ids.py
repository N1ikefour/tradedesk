"""UUID v7 (RFC 9562) — в stdlib Python 3.12 его нет, отдельная зависимость ради него не нужна.

Зачем v7, а не v4: старшие 48 бит — время в миллисекундах, поэтому идентификаторы монотонно
возрастают, и вставки идут в конец B-tree, а не в случайные листья. На `positions` это разница
в скорости вставки и в раздувании индекса.
"""

from __future__ import annotations

import os
import threading
import time
from uuid import UUID

_VERSION = 0x7
_VARIANT_RFC_4122 = 0b10

# rand_a (12 бит) занят счётчиком: он даёт монотонность внутри одной миллисекунды
# (RFC 9562, 6.2, «Fixed Bit-Length Dedicated Counter»).
_COUNTER_BITS = 12
_COUNTER_MAX = (1 << _COUNTER_BITS) - 1
_TIMESTAMP_MASK = (1 << 48) - 1
_RANDOM_MASK = (1 << 62) - 1

_lock = threading.Lock()
_last_timestamp_ms = 0
_counter = 0


def _now_ms() -> int:
    """Источник времени отдельной функцией: тесты подменяют его, а не глобальный `time`."""
    return time.time_ns() // 1_000_000


def _next_tick() -> tuple[int, int]:
    """Время и счётчик, строго возрастающие как пара, даже если часы отпрыгнули назад."""
    global _last_timestamp_ms, _counter

    with _lock:
        now_ms = _now_ms()
        if now_ms > _last_timestamp_ms:
            _last_timestamp_ms = now_ms
            _counter = 0
        elif _counter < _COUNTER_MAX:
            _counter += 1
        else:
            # Счётчик переполнен: занимаем следующую миллисекунду, часы её догонят.
            _last_timestamp_ms += 1
            _counter = 0
        return _last_timestamp_ms, _counter


def uuid7() -> UUID:
    """UUID версии 7. Два подряд вызова дают возрастающие значения."""
    timestamp_ms, counter = _next_tick()
    value = (timestamp_ms & _TIMESTAMP_MASK) << 80
    value |= _VERSION << 76
    value |= counter << 64
    value |= _VARIANT_RFC_4122 << 62
    value |= int.from_bytes(os.urandom(8), "big") & _RANDOM_MASK
    return UUID(int=value)


def uuid7_timestamp_ms(value: UUID) -> int:
    """Время создания идентификатора в миллисекундах UNIX. Для отладки и тестов."""
    return value.int >> 80
