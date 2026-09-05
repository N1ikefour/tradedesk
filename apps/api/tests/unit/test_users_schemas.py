"""Валидация тела PATCH /users/me (S0-08)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.domains.users.schemas import (
    DAY_BOUNDARY_HOUR_MAX,
    DAY_BOUNDARY_HOUR_MIN,
    DISPLAY_NAME_MAX_LENGTH,
    UserUpdateRequest,
    known_timezones,
)


def build(**payload: Any) -> UserUpdateRequest:
    """Через model_validate: так тело приходит из JSON, а не из kwargs."""
    return UserUpdateRequest.model_validate(payload)


def first_error(payload: dict[str, Any]) -> tuple[str, str]:
    with pytest.raises(ValidationError) as error:
        UserUpdateRequest.model_validate(payload)
    reported = error.value.errors()[0]
    return str(reported["loc"][0]), str(reported["msg"])


# --- частичность -------------------------------------------------------------


def test_empty_body_sets_nothing() -> None:
    """Пустое тело — не «сбросить всё», а «ничего не менять»."""
    assert build().model_fields_set == set()


def test_absent_field_differs_from_explicit_null() -> None:
    """Разница, ради которой PATCH существует: «не трогай» против «очисти»."""
    assert build(timezone="UTC").model_fields_set == {"timezone"}
    assert build(display_name=None).model_fields_set == {"display_name"}
    assert build().model_dump(exclude_unset=True) == {}
    assert build(display_name=None).model_dump(exclude_unset=True) == {"display_name": None}


def test_unknown_field_is_rejected() -> None:
    """Опечатка в имени поля не должна выглядеть как успешное сохранение."""
    with pytest.raises(ValidationError):
        build(timeZone="UTC")


# --- display_name ------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Ник  ", "Ник"),
        ("Ник", "Ник"),
        ("", None),
        ("   ", None),
        ("\t\n ", None),
        # Неразрывный пробел тоже пробел: имя из него — отсутствие имени.
        ("\xa0", None),
        (None, None),
        ("x" * DISPLAY_NAME_MAX_LENGTH, "x" * DISPLAY_NAME_MAX_LENGTH),
    ],
)
def test_display_name_normalized(raw: str | None, expected: str | None) -> None:
    assert build(display_name=raw).display_name == expected


@pytest.mark.parametrize(
    "raw",
    [
        "x" * (DISPLAY_NAME_MAX_LENGTH + 1),
        "Ник\x00",
        "Ник\nBcc: someone@evil.test",
        "Ник\x1b[31m",
        "Ник\x9b",
    ],
)
def test_display_name_rejected(raw: str) -> None:
    field, message = first_error({"display_name": raw})

    assert field == "display_name"
    assert "Value error" not in message


# --- timezone ----------------------------------------------------------------


@pytest.mark.parametrize("raw", ["Europe/Moscow", "UTC", "America/New_York", " Asia/Tokyo "])
def test_timezone_accepts_iana_names(raw: str) -> None:
    assert build(timezone=raw).timezone == raw.strip()


@pytest.mark.parametrize(
    "raw",
    [
        # Смещение ломается на переходе на летнее время — принимать нельзя.
        "UTC+3",
        "UTC+03:00",
        "GMT+3",
        "+03:00",
        "MSK",
        "Europe/Moskva",
        # Регистр значим: на macOS файловая система регистронезависима, и `ZoneInfo`
        # приняла бы это — валидация обязана решать одинаково с контейнером.
        "europe/moscow",
        "",
        "   ",
        "../../etc/passwd",
        "Europe/Moscow\x00",
    ],
)
def test_timezone_rejected(raw: str) -> None:
    field, message = first_error({"timezone": raw})

    assert field == "timezone"
    assert "Value error" not in message


def test_timezone_null_is_rejected() -> None:
    """Колонка NOT NULL: `null` не должен молча означать «не трогать»."""
    field, _ = first_error({"timezone": None})

    assert field == "timezone"


def test_known_timezones_are_present() -> None:
    """Пустая база tzdata в образе отвергала бы вообще любую таймзону — молча."""
    zones = known_timezones()

    assert {"UTC", "Europe/Moscow", "America/New_York"} <= zones
    assert "UTC+3" not in zones


# --- day_boundary_hour -------------------------------------------------------


@pytest.mark.parametrize("raw", [DAY_BOUNDARY_HOUR_MIN, 7, DAY_BOUNDARY_HOUR_MAX])
def test_day_boundary_hour_accepts_range(raw: int) -> None:
    assert build(day_boundary_hour=raw).day_boundary_hour == raw


@pytest.mark.parametrize(
    "raw",
    [DAY_BOUNDARY_HOUR_MIN - 1, DAY_BOUNDARY_HOUR_MAX + 1, 100, -100, 7.5, "07:00", "", None],
)
def test_day_boundary_hour_rejected(raw: object) -> None:
    field, _ = first_error({"day_boundary_hour": raw})

    assert field == "day_boundary_hour"


def test_day_boundary_hour_accepts_numeric_string() -> None:
    """Значение поля формы приходит строкой; приведение pydantic здесь оставлено намеренно.

    Диапазон всё равно проверяется после приведения, поэтому «7» не обходит валидацию.
    """
    assert build(day_boundary_hour="7").day_boundary_hour == 7
    with pytest.raises(ValidationError):
        build(day_boundary_hour="24")
