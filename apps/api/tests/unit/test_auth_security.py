"""Примитивы auth: код, его хеш, идентификатор сессии (S0-04)."""

from __future__ import annotations

import pytest

from app.domains.auth import security


def test_code_is_six_digits() -> None:
    codes = {security.generate_code() for _ in range(200)}

    assert all(len(code) == security.CODE_LENGTH and code.isdigit() for code in codes)
    # 200 значений из миллиона: совпадений почти нет, вырожденный генератор виден сразу.
    assert len(codes) > 150


def test_code_keeps_leading_zeros(monkeypatch: pytest.MonkeyPatch) -> None:
    """Код — строка: `int` превратил бы 000007 в 7, и такой код не совпал бы с введённым."""
    monkeypatch.setattr(security.secrets, "randbelow", lambda _upper: 7)

    assert security.generate_code() == "000007"


def test_hash_depends_on_pepper() -> None:
    assert security.hash_code("123456", "pepper-a") != security.hash_code("123456", "pepper-b")


def test_hash_is_sha256_hex() -> None:
    digest = security.hash_code("123456", "pepper")

    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


def test_code_matches_only_on_equal_code() -> None:
    expected = security.hash_code("123456", "pepper")

    assert security.code_matches("123456", "pepper", expected)
    assert not security.code_matches("123457", "pepper", expected)
    assert not security.code_matches("123456", "другой pepper", expected)


def test_session_id_is_uuid4() -> None:
    """uuid7 опубликовал бы время создания сессии прямо в значении cookie."""
    ids = [security.new_session_id() for _ in range(50)]

    assert {value.version for value in ids} == {4}
    assert len(set(ids)) == 50


def test_rate_limit_subject_hides_email() -> None:
    subject = security.hash_rate_limit_subject("user@example.com", "pepper")

    assert "user@example.com" not in subject
    assert subject != security.hash_rate_limit_subject("user@example.com", "другой pepper")
    assert subject == security.hash_rate_limit_subject("user@example.com", "pepper")
