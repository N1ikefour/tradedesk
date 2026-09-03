"""Точка входа API: сборка приложения, логи, обработчики ошибок, жизненный цикл."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.core.config import Settings, get_settings
from app.core.db import dispose_engine
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.redis import close_redis
from app.domains.system.router import router as system_router

API_PREFIX = "/api/v1"

log = get_logger(__name__)


def _init_sentry(settings: Settings) -> bool:
    """Sentry поднимается только при непустом DSN. Его отсутствие — штатный режим."""
    dsn = settings.sentry_dsn.get_secret_value().strip()
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(dsn=dsn, environment=settings.app_env, release=__version__)
    return True


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # В лог идёт присутствие секретов, не значения (DEVELOPER_MANUAL.md 11.1).
    log.info(
        "app.started",
        app_env=settings.app_env,
        version=__version__,
        sentry="enabled" if _init_sentry(settings) else "disabled",
        secrets=settings.secret_presence(),
    )
    try:
        yield
    finally:
        await dispose_engine()
        await close_redis()
        log.info("app.stopped")


def create_app() -> FastAPI:
    """Гейты конфигурации отрабатывают здесь — до старта сервера и первого запроса."""
    settings = get_settings()
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        # Схема и доки живут под тем же префиксом, что и API.
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
    )
    register_error_handlers(app)
    app.include_router(system_router, prefix=API_PREFIX)
    return app


app = create_app()
