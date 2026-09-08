"""Общие фикстуры. Integration-тесты пропускаются, когда Docker недоступен."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import AsyncIterator, Callable, Iterator
from functools import lru_cache

import pytest
from fastapi import FastAPI

from app.core import db as db_module
from app.core import queue as queue_module
from app.core import redis as redis_module
from app.core.config import Settings, get_settings
from app.core.db import ensure_test_database

# Порт, на котором заведомо никто не слушает: зависимость «недоступна» без ожидания сети.
UNREACHABLE_DB_URL = "postgresql+asyncpg://td:td@127.0.0.1:1/td_test"
UNREACHABLE_REDIS_URL = "redis://127.0.0.1:1/0"

# base64 от b"tradedesk-test-master-key-32byte" — ровно 32 байта, как требует S0-05.
TEST_MASTER_KEY = "dHJhZGVkZXNrLXRlc3QtbWFzdGVyLWtleS0zMmJ5dGU="


@lru_cache(maxsize=1)
def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Пропуск с явной причиной: молча зелёный сьют без Docker вводил бы в заблуждение."""
    if docker_available():
        return
    skip = pytest.mark.skip(reason="Docker недоступен: integration-тесты пропущены")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session", autouse=True)
def guard_test_database() -> Iterator[None]:
    """Ни один движок в тестах не создаётся до проверки имени БД.

    Guard как отдельная функция ничего не защищает: его надо поставить на путь создания
    движка. Здесь — единственное место, через которое тесты получают соединение.
    """
    original = db_module.create_engine

    def guarded(settings: Settings) -> object:
        ensure_test_database(settings.database_url.get_secret_value())
        return original(settings)

    db_module.create_engine = guarded  # type: ignore[assignment]
    try:
        yield
    finally:
        db_module.create_engine = original


@pytest.fixture(autouse=True)
async def reset_app_state() -> AsyncIterator[None]:
    """Конфиг и клиенты — синглтоны; между тестами их надо сбрасывать.

    Пул очереди arq тут наравне с остальными: он помнит номер базы Redis из DSN, и
    оставленный от прошлого модуля пул ставил бы задачи в чужой контейнер.
    """
    get_settings.cache_clear()
    await db_module.dispose_engine()
    await redis_module.close_redis()
    await queue_module.close_queue()
    yield
    get_settings.cache_clear()
    await db_module.dispose_engine()
    await redis_module.close_redis()
    await queue_module.close_queue()


@pytest.fixture
def local_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Минимальное валидное окружение local. Тест меняет только то, что проверяет."""
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    # Валидный по формату ключ (base64 от 32 байт), а не просто непустая строка:
    # с S0-05 create_app в проде отказывается грузиться на непригодном MASTER_KEY.
    monkeypatch.setenv("MASTER_KEY", TEST_MASTER_KEY)
    monkeypatch.setenv("OTP_PEPPER", "test-otp-pepper")
    monkeypatch.setenv("COLLECTOR_TOKEN", "test-collector-token")
    monkeypatch.setenv("SENTRY_DSN", "")
    yield monkeypatch


@pytest.fixture
def make_app() -> Callable[[], FastAPI]:
    """Фабрика, а не готовое приложение: тест сначала правит окружение, потом собирает."""

    def factory() -> FastAPI:
        from app.main import create_app

        return create_app()

    return factory


@pytest.fixture
def unreachable_env(local_env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Зависимости смотрят в закрытый порт: недоступность без ожидания сети."""
    local_env.setenv("DATABASE_URL", UNREACHABLE_DB_URL)
    local_env.setenv("REDIS_URL", UNREACHABLE_REDIS_URL)
    return local_env
