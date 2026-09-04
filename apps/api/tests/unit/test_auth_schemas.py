"""Валидация тел запросов auth (S0-04)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domains.auth.schemas import RequestCodeRequest, VerifyRequest, normalize_email


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  User@Example.COM  ", "user@example.com"),
        ("a.b+tag@sub.example.co.uk", "a.b+tag@sub.example.co.uk"),
        ("o'brien@example.com", "o'brien@example.com"),
        # IDN: буквы вне ASCII запрещать нельзя, вырезаются только управляющие символы.
        ("Почта@пример.рф", "почта@пример.рф"),
    ],
)
def test_email_is_normalized(raw: str, expected: str) -> None:
    assert RequestCodeRequest(email=raw).email == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "no-at-sign",
        "no@domain",
        "two@@example.com",
        "spaces in@example.com",
        "user@example.com\nBcc: someone@evil.test",
        "a" * 250 + "@example.com",
        # Управляющие символы: `\s` ловит не все, а в заголовке письма опасен любой.
        "user\x00@example.com",
        "user\x07@example.com",
        "user\x1b@example.com",
        "user@example\x7f.com",
        "user@example.com\x9b",
    ],
)
def test_bad_email_rejected(raw: str) -> None:
    with pytest.raises(ValidationError):
        RequestCodeRequest(email=raw)
    with pytest.raises(ValueError, match="Некорректный адрес"):
        normalize_email(raw)


def test_message_has_no_pydantic_prefix() -> None:
    """Сообщение уходит в UI как есть: приставка «Value error, » там не нужна."""
    with pytest.raises(ValidationError) as error:
        RequestCodeRequest(email="not-an-email")

    assert error.value.errors()[0]["msg"] == "Некорректный адрес электронной почты"


def test_verify_accepts_six_digits() -> None:
    payload = VerifyRequest(email="user@example.com", code=" 000123 ")

    assert payload.code == "000123"


@pytest.mark.parametrize("raw", ["", "12345", "1234567", "12345a", "12 34 56", "9" * 200])
def test_verify_rejects_malformed_code(raw: str) -> None:
    with pytest.raises(ValidationError):
        VerifyRequest(email="user@example.com", code=raw)
