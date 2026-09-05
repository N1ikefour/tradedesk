"""Скраб свободного текста из внешних источников — X-21, `app/core/text.py`."""

from __future__ import annotations

import pytest

from app.core.logging import MIN_SCRUBBED_SECRET_LENGTH, REDACTED, register_secret_values
from app.core.text import ELLIPSIS, MAX_EXTERNAL_TEXT_LENGTH, sanitize_external_text

COLLECTOR_TOKEN = "collector-token-8f1c2d"


@pytest.fixture(autouse=True)
def _registered_secrets() -> None:
    assert len(COLLECTOR_TOKEN) >= MIN_SCRUBBED_SECRET_LENGTH
    register_secret_values([COLLECTOR_TOKEN])


def test_known_secret_is_cut_out() -> None:
    """Ровно то, ради чего скраб и ставится на запись: секрет не доезжает до поля."""
    sanitized = sanitize_external_text(f"MT5 отверг вход, token={COLLECTOR_TOKEN}")

    assert sanitized is not None
    assert COLLECTOR_TOKEN not in sanitized
    assert REDACTED in sanitized
    # Диагностируемость сохраняется: остальной текст на месте.
    assert "MT5 отверг вход" in sanitized


def test_control_characters_and_newlines_collapse() -> None:
    """Строка уезжает в JSON-лог одной строкой и в UI без разметки."""
    sanitized = sanitize_external_text("первая\nвторая\r\n\tтретья\x00четвёртая")

    assert sanitized == "первая вторая третья четвёртая"


def test_secret_broken_by_a_control_character_is_still_cut() -> None:
    """Порядок операций: скраб идёт до нормализации пробелов, а не после.

    Иначе управляющий символ, вставленный в середину секрета, разрывал бы подстроку
    ровно так, чтобы `scrub_text` перестал её узнавать.
    """
    assert sanitize_external_text(COLLECTOR_TOKEN) == REDACTED


def test_long_text_is_truncated_to_the_limit() -> None:
    sanitized = sanitize_external_text("я" * (MAX_EXTERNAL_TEXT_LENGTH + 50))

    assert sanitized is not None
    assert len(sanitized) == MAX_EXTERNAL_TEXT_LENGTH
    assert sanitized.endswith(ELLIPSIS)


def test_secret_at_the_tail_is_cut_before_truncation() -> None:
    """Обрезка последней: обрежь раньше — и хвост секрета уехал бы мимо проверки."""
    sanitized = sanitize_external_text("х" * MAX_EXTERNAL_TEXT_LENGTH + COLLECTOR_TOKEN)

    assert sanitized is not None
    assert COLLECTOR_TOKEN not in sanitized
    # Секрет вырезан до обрезки, поэтому от него не осталось и префикса.
    assert COLLECTOR_TOKEN[:MIN_SCRUBBED_SECRET_LENGTH] not in sanitized


@pytest.mark.parametrize("value", [None, "", "   ", "\n\t", "\x00"])
def test_nothing_to_show_becomes_none(value: str | None) -> None:
    """Пустая строка в `status_message` — это красный статус без причины."""
    assert sanitize_external_text(value) is None
