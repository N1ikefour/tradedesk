"""Общие фикстуры. Integration-тесты пропускаются, когда Docker недоступен."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import AsyncIterator, Callable, Iterator
from functools import lru_cache

import pytest
from fastapi import FastAPI

from app.core import db as db_module
from app.core import redis as redis_module
from app.core.config import get_settings

# Порт, на котором заведомо никто не слушает: зависимость «недоступна» без ожидания сети.
UNREACHABLE_DB_URL = "postgresql+asyncpg://td:td@127.0.0.1:1/td"
UNREACHABLE_REDIS_URL = "redis://127.0.0.1:1/0"


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


@pytest.fixture(autouse=True)
async def reset_app_state() -> AsyncIterator[None]:
    """Конфиг и клиенты — синглтоны; между тестами их надо сбрасывать."""
    get_settings.cache_clear()
    await db_module.dispose_engine()
    await redis_module.close_redis()
    yield
    get_settings.cache_clear()
    await db_module.dispose_engine()
    await redis_module.close_redis()


@pytest.fixture
def local_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Минимальное валидное окружение local. Тест меняет только то, что проверяет."""
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("MASTER_KEY", "test-master-key")
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
