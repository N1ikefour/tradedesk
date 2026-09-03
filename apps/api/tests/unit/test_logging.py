"""Логи не выдают секретов — ни по имени ключа, ни внутри текста исключения."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
import structlog
from fastapi import FastAPI

from app.core.logging import (
    REDACTED,
    configure_logging,
    get_logger,
    register_secret_values,
    scrub_text,
)

DSN_WITH_PASSWORD = "postgresql://td:hunter2@db.internal:5432/td"


@pytest.fixture(autouse=True)
def _reset_registered_secrets() -> None:
    register_secret_values([])


def test_scrub_text_hides_password_in_dsn() -> None:
    scrubbed = scrub_text(f"connection failed: {DSN_WITH_PASSWORD}")

    assert "hunter2" not in scrubbed
    # Хост остаётся: без него сообщение бесполезно для диагностики.
    assert "db.internal" in scrubbed
    assert REDACTED in scrubbed


def test_scrub_text_hides_registered_secret_value() -> None:
    register_secret_values(["super-secret-token"])

    assert "super-secret-token" not in scrub_text("token=super-secret-token")


def test_scrub_text_ignores_short_values() -> None:
    """Короткая подстрока встречается в осмысленном тексте — вырезать её нельзя."""
    register_secret_values(["td"])

    assert scrub_text("подключение к td") == "подключение к td"


def test_log_line_is_json_and_censors_secret_keys(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging()
    get_logger("test").info("probe", secret_key="значение-секрета", host="localhost")

    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert line["event"] == "probe"
    assert line["secret_key"] == REDACTED
    assert line["host"] == "localhost"


def test_traceback_does_not_leak_dsn_password(capsys: pytest.CaptureFixture[str]) -> None:
    """Регрессия на находку ревью S0-02: цензура по имени ключа не спасала от текста
    исключения — format_exc_info рендерит traceback в поле `exception`."""
    configure_logging()
    try:
        raise RuntimeError(f"connection failed: {DSN_WITH_PASSWORD}")
    except RuntimeError:
        get_logger("test").exception("api.unhandled_exception")

    output = capsys.readouterr().out

    assert "hunter2" not in output
    assert "connection failed" in output


def test_registered_secret_never_appears_in_output(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(secret_values=["ОЧЕНЬ-СЕКРЕТНОЕ-ЗНАЧЕНИЕ"])
    get_logger("test").info("что-то пошло не так: ОЧЕНЬ-СЕКРЕТНОЕ-ЗНАЧЕНИЕ")

    assert "ОЧЕНЬ-СЕКРЕТНОЕ-ЗНАЧЕНИЕ" not in capsys.readouterr().out


async def test_lifespan_logs_presence_not_values(
    local_env: pytest.MonkeyPatch,
    make_app: Callable[[], FastAPI],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """lifespan не исполняется под ASGITransport, поэтому проверяется отдельно."""
    secret = "ЗНАЧЕНИЕ-КОТОРОГО-НЕ-ДОЛЖНО-БЫТЬ-В-ЛОГАХ"
    local_env.setenv("SECRET_KEY", secret)
    local_env.setenv("MASTER_KEY", "")
    local_env.setenv("DATABASE_URL", "postgresql+asyncpg://td:пароль-бд@127.0.0.1:1/td_test")

    from app.main import lifespan

    app = make_app()
    async with lifespan(app):
        pass

    output = capsys.readouterr().out
    started = next(json.loads(line) for line in output.splitlines() if '"app.started"' in line)

    assert secret not in output
    assert "пароль-бд" not in output
    assert started["secrets"]["SECRET_KEY"] == "present"
    assert started["secrets"]["MASTER_KEY"] == "MISSING"
    assert started["sentry"] == "disabled"


def teardown_module() -> None:
    """Возвращаем логгер в исходное состояние: configure_logging меняет глобальный root."""
    structlog.reset_defaults()
