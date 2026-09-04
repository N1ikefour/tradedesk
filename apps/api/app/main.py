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
from app.core.origin import OriginCheckMiddleware
from app.core.redis import close_redis
from app.core.security import check_master_key, master_key_scrub_values
from app.domains.auth.router import router as auth_router
from app.domains.mail.provider import check_email_provider
from app.domains.mail.router import router as dev_router
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
    # Инициализация — отдельным шагом: побочный эффект внутри аргумента log.info прятал бы
    # причину падения Sentry SDK за строчкой логирования.
    sentry_enabled = _init_sentry(settings)
    # В лог идёт присутствие секретов, не значения (DEVELOPER_MANUAL.md 11.1).
    log.info(
        "app.started",
        app_env=settings.app_env,
        version=__version__,
        sentry="enabled" if sentry_enabled else "disabled",
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
    # Значения секретов передаются логгеру, чтобы он вырезал их из любого текста,
    # включая traceback: цензура по имени ключа не спасает от текста исключения.
    # Мастер-ключ регистрируется и в байтовых написаниях: в коде он живёт как `bytes`,
    # а скраб ищет подстроку — с base64 из конфига repr(b"...") не совпал бы.
    configure_logging(
        secret_values=[*settings.scrubbable_secret_values(), *master_key_scrub_values(settings)]
    )
    # Отсутствующий провайдер писем — отказ на старте, а не 500 на первом входе.
    check_email_provider(settings)
    # Битый MASTER_KEY — тоже отказ на старте, а не 500 на первой записи credentials (S1-06).
    check_master_key(settings)

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
    # CSRF из SPEC.md 4: проверка Origin распространяется на все мутирующие запросы.
    app.add_middleware(OriginCheckMiddleware, app_url=settings.app_url)
    app.include_router(system_router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    if not settings.is_prod:
        # Письма с кодами наружу не выставляются: в проде маршрута просто нет,
        # он не появляется и в OpenAPI.
        app.include_router(dev_router, prefix=API_PREFIX)
    return app


app = create_app()
