"""Генератор UUID v7 (app/core/ids.py)."""

from __future__ import annotations

import time
from uuid import RFC_4122

import pytest

from app.core import ids
from app.core.ids import uuid7, uuid7_timestamp_ms


def test_version_and_variant_are_v7() -> None:
    value = uuid7()

    assert value.version == 7
    # Вариант RFC 4122: старшие два бита восьмого байта равны 0b10.
    assert value.variant == RFC_4122


def test_consecutive_ids_increase() -> None:
    """Монотонность — единственная причина брать v7 вместо v4: вставки идут в конец B-tree."""
    values = [uuid7() for _ in range(1000)]

    assert values == sorted(values)
    assert len(set(values)) == len(values)


def test_string_form_sorts_like_value() -> None:
    """Сортировка по тексту и по значению совпадают: важно для курсорной пагинации."""
    values = [uuid7() for _ in range(100)]

    assert [str(value) for value in values] == sorted(str(value) for value in values)


def test_timestamp_is_current_time() -> None:
    before = time.time_ns() // 1_000_000
    value = uuid7()
    after = time.time_ns() // 1_000_000

    assert before <= uuid7_timestamp_ms(value) <= after


def test_random_tail_differs_within_one_millisecond() -> None:
    """Счётчик даёт порядок, случайный хвост — неугадываемость."""
    tails = {uuid7().int & ((1 << 62) - 1) for _ in range(100)}

    assert len(tails) == 100


def test_counter_exhaustion_borrows_next_millisecond(monkeypatch: pytest.MonkeyPatch) -> None:
    """12-битный счётчик — 4096 значений на миллисекунду; 4097-е занимает следующую."""
    frozen_ms = 1_700_000_000_000
    monkeypatch.setattr(ids, "_now_ms", lambda: frozen_ms)
    monkeypatch.setattr(ids, "_last_timestamp_ms", 0)
    monkeypatch.setattr(ids, "_counter", 0)

    values = [uuid7() for _ in range(ids._COUNTER_MAX + 2)]
    timestamps = [uuid7_timestamp_ms(value) for value in values]

    assert values == sorted(values)
    assert len(set(values)) == len(values)
    # Часы стоят, а идентификаторы всё равно растут — это и есть работа счётчика.
    assert set(timestamps[:-1]) == {frozen_ms}
    assert timestamps[-1] == frozen_ms + 1


def test_clock_going_backwards_still_increases(monkeypatch: pytest.MonkeyPatch) -> None:
    """Часы прыгнули назад (ntp, перевод времени): порядок обязан сохраниться."""
    clock = iter([2_000_000_000_000, 1_000_000_000_000, 1_000_000_000_000])
    monkeypatch.setattr(ids, "_now_ms", lambda: next(clock))
    monkeypatch.setattr(ids, "_last_timestamp_ms", 0)
    monkeypatch.setattr(ids, "_counter", 0)

    first, second, third = uuid7(), uuid7(), uuid7()

    assert first < second < third
    # Метка времени не откатывается назад вслед за часами.
    assert uuid7_timestamp_ms(third) == uuid7_timestamp_ms(first) == 2_000_000_000_000
