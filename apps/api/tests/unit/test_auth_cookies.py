"""Атрибуты cookie сессии — SPEC.md 4, пункт 3 (S0-04)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

import pytest
from starlette.responses import Response

from app.core.config import Settings
from app.domains.auth.cookies import (
    SESSION_COOKIE_NAME,
    clear_session_cookie,
    set_session_cookie,
)

SESSION_ID = UUID("0192f8a0-1111-4222-8333-444455556666")
# 30 суток из SPEC.md 4: число фиксируется тестом, а не берётся из константы приложения.
MAX_AGE = 2592000


def _set(app_env: Literal["local", "prod"]) -> str:
    response = Response()
    set_session_cookie(response, Settings(app_env=app_env), SESSION_ID)
    return response.headers["set-cookie"]


def _clear(app_env: Literal["local", "prod"]) -> str:
    response = Response()
    clear_session_cookie(response, Settings(app_env=app_env))
    return response.headers["set-cookie"]


@pytest.mark.parametrize("app_env", ["local", "prod"])
def test_cookie_carries_spec_attributes(app_env: Literal["local", "prod"]) -> None:
    header = _set(app_env)

    assert header.startswith(f"{SESSION_COOKIE_NAME}={SESSION_ID}; ")
    assert "HttpOnly" in header
    assert f"Max-Age={MAX_AGE}" in header
    assert "Path=/" in header
    assert "SameSite=lax" in header


def test_secure_is_set_in_prod() -> None:
    """Положительная половина условия: без неё мутация `secure=False` проходит незамеченной."""
    assert "; Secure" in _set("prod")
    assert "; Secure" in _clear("prod")


def test_secure_is_absent_in_local() -> None:
    """Secure на http://localhost браузер отбрасывает вместе с самой cookie."""
    assert "Secure" not in _set("local")
    assert "Secure" not in _clear("local")


@pytest.mark.parametrize("app_env", ["local", "prod"])
def test_clear_repeats_the_attributes_of_set(app_env: Literal["local", "prod"]) -> None:
    """Расхождение атрибутов оставило бы в браузере вторую живую cookie того же имени."""
    header = _clear(app_env)

    assert "HttpOnly" in header
    assert "Path=/" in header
    assert "SameSite=lax" in header
    assert "Max-Age=0" in header
