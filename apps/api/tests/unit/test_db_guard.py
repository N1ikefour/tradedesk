"""Guard тестовой БД: исключение бросается до первого запроса (SPEC.md 13)."""

from __future__ import annotations

import pytest

from app.core.db import (
    DatabaseGuardError,
    ensure_test_database,
    get_engine,
    mask_database_url,
)


def test_guard_raises_on_non_test_database() -> None:
    with pytest.raises(DatabaseGuardError) as excinfo:
        ensure_test_database("postgresql+asyncpg://td:td@localhost:5432/td")

    assert "_test" in str(excinfo.value)


def test_guard_raises_on_production_looking_name() -> None:
    with pytest.raises(DatabaseGuardError):
        ensure_test_database("postgresql+asyncpg://td:td@db.example.com:5432/tradedesk_prod")


def test_guard_passes_on_test_database() -> None:
    ensure_test_database("postgresql+asyncpg://td:td@localhost:5432/td_test")


def test_guard_rejects_unparsable_url() -> None:
    with pytest.raises(DatabaseGuardError):
        ensure_test_database("это не url")


def test_guard_message_hides_password() -> None:
    with pytest.raises(DatabaseGuardError) as excinfo:
        ensure_test_database("postgresql+asyncpg://td:hunter2@localhost:5432/td")

    assert "hunter2" not in str(excinfo.value)


def test_mask_database_url_hides_password() -> None:
    masked = mask_database_url("postgresql+asyncpg://td:hunter2@localhost:5432/td")

    assert "hunter2" not in masked
    assert "localhost" in masked


def test_suite_refuses_engine_for_non_test_database(
    local_env: pytest.MonkeyPatch,
) -> None:
    """Guard стоит на пути создания движка, а не лежит непозванной функцией.

    Ревью S0-02 показало: без этой проверки сьют молча подключался к базе `tradedesk_prod`.
    """
    local_env.setenv("DATABASE_URL", "postgresql+asyncpg://td:td@127.0.0.1:1/tradedesk_prod")

    with pytest.raises(DatabaseGuardError):
        get_engine()
