"""Async-SQLAlchemy: движок, сессии, guard тестовой БД."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from sqlalchemy import MetaData, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError, DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Имя тестовой БД обязано содержать эту подстроку (SPEC.md 13, CLAUDE.md 6).
TEST_DATABASE_MARKER = "_test"

PING_TIMEOUT_SECONDS = 2.0

# Параметризованный SQL длинный, а для диагностики хватает начала.
MAX_LOGGED_STATEMENT_LENGTH = 500


# Без этого имена ограничений придумывает Postgres, и `downgrade` в следующих задачах
# приходится писать по факту, а не по модели. Задаётся один раз, до первой миграции.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Общий declarative-базис. Таблицы — в `app/domains/*/models.py`."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class DatabaseGuardError(RuntimeError):
    """Попытка работать не с тестовой БД из тестового окружения."""


def mask_database_url(url: str) -> str:
    """URL без пароля — единственная форма, пригодная для логов и сообщений об ошибках."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except ArgumentError:
        return "<DATABASE_URL не разбирается>"


def ensure_test_database(url: str) -> None:
    """Бросает исключение, если БД не тестовая. Вызывается до первого запроса к ней."""
    try:
        parsed = make_url(url)
    except ArgumentError as exc:
        raise DatabaseGuardError(f"DATABASE_URL не разбирается как URL: {exc}") from exc

    database = parsed.database or ""
    if TEST_DATABASE_MARKER not in database:
        raise DatabaseGuardError(
            f"Тесты работают только с БД, имя которой содержит {TEST_DATABASE_MARKER!r}. "
            f"Получено имя {database!r} (url: {mask_database_url(url)})"
        )


def create_engine(settings: Settings) -> AsyncEngine:
    """Создание движка не открывает соединений: asyncpg подключается лениво.

    `hide_parameters`: SQLAlchemy вкладывает bound parameters в текст `StatementError`,
    а обработчик необработанных исключений печатает traceback целиком. Без этого флага
    в лог уезжает всё, что участвовало в упавшем запросе, — код входа, адрес почты,
    а позже и содержимое `account_credentials`.
    """
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        hide_parameters=True,
    )


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings())
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-зависимость: сессия на запрос."""
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    """Закрывает пул и сбрасывает синглтоны — следующий get_engine() перечитает конфиг."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def describe_database_error(exc: BaseException) -> dict[str, str] | None:
    """Портрет ошибки БД, пригодный для логов. `None` — если ошибка не про БД.

    Текст такой ошибки печатать нельзя ни в каком виде: SQLAlchemy вкладывает в него
    bound parameters, а Postgres — свой `DETAIL: Failing row contains (…)`, и второе
    не убирается `hide_parameters`. В обоих случаях наружу поехало бы содержимое строки:
    код входа, адрес почты, а позже расшифрованные credentials счёта.

    Взамен берётся то, что значений не содержит: тип, SQLSTATE, имя ограничения и SQL
    с плейсхолдерами. Traceback теряется — место падения показывают `path` и `method`.
    """
    if not isinstance(exc, DBAPIError):
        return None
    origin = exc.orig
    described = {"db_error_type": type(origin if origin is not None else exc).__name__}
    statement = exc.statement or ""
    if statement:
        described["db_statement"] = statement[:MAX_LOGGED_STATEMENT_LENGTH]
    for attribute, key in (("sqlstate", "db_sqlstate"), ("constraint_name", "db_constraint")):
        value = getattr(origin, attribute, None)
        if value:
            described[key] = str(value)
    return described


async def check_database() -> bool:
    """Проверка живости для /health. Недоступность зависимости — не ошибка приложения."""
    try:
        async with asyncio.timeout(PING_TIMEOUT_SECONDS):
            async with get_engine().connect() as connection:
                await connection.execute(text("SELECT 1"))
    except Exception as exc:
        # Текст исключения asyncpg может содержать DSN — в лог идёт только тип.
        log.warning("health.db_unavailable", error_type=type(exc).__name__)
        return False
    return True
