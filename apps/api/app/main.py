"""Точка входа API: сборка приложения, логи, обработчики ошибок, жизненный цикл."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.core.client_ip import check_trusted_proxies, trusted_proxies
from app.core.config import Settings, get_settings
from app.core.db import dispose_engine
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger
from app.core.openapi import install_error_responses
from app.core.origin import OriginCheckMiddleware
from app.core.redis import close_redis
from app.core.security import check_master_key, master_key_scrub_values
from app.domains.accounts.router import router as accounts_router
from app.domains.analytics.router import router as analytics_router
from app.domains.auth.router import router as auth_router
from app.domains.collector.router import router as collector_router
from app.domains.journal.router import router as journal_router
from app.domains.mail.provider import check_email_provider
from app.domains.mail.router import router as dev_router
from app.domains.system.router import router as system_router
from app.domains.users.router import router as users_router

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
    if not trusted_proxies(settings):
        # X-06: без списка доверенных прокси лимит по IP считается по адресу соединения.
        # За прокси это один адрес на всех, и лимит становится общим на всю установку —
        # молчать об этом нельзя, но и доверять заголовку «на всякий случай» тоже.
        log.warning(
            "app.trusted_proxies_unset",
            hint=(
                "TRUSTED_PROXIES не задан: X-Forwarded-For не читается, лимит по IP считается "
                "по адресу соединения. За прокси он окажется общим на всех пользователей"
            ),
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
    # Непригодный TRUSTED_PROXIES — отказ на старте: опечатка в адресе прокси иначе тихо
    # возвращает лимит по IP к общему на всю установку (X-06).
    check_trusted_proxies(settings)

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
    # Тот же формат ошибок — в OpenAPI (ADR-0004). Без этого схема обещает фронту
    # `422 HTTPValidationError`, которого приложение не отдаёт, и не знает ни одного
    # кода из словаря SPEC.md 5.1.
    install_error_responses(app)
    # CSRF из SPEC.md 4: проверка Origin распространяется на все мутирующие запросы.
    app.add_middleware(OriginCheckMiddleware, app_url=settings.app_url)
    app.include_router(system_router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(users_router, prefix=API_PREFIX)
    app.include_router(accounts_router, prefix=API_PREFIX)
    app.include_router(journal_router, prefix=API_PREFIX)
    # Своего префикса у роутера нет: сводка живёт под `/analytics`, а календарь остаётся
    # на своём пути из SPEC.md 5.4 (`/journal/calendar`) — считает их один домен.
    app.include_router(analytics_router, prefix=API_PREFIX)
    # Маршруты коллектора: сессии у них нет, авторизация — сервисный токен. Живут под тем
    # же префиксом, что и остальной API (CLAUDE.md §5), и в OpenAPI остаются намеренно —
    # это контракт для S1-08, а пароль в схеме присутствует как тип, а не как значение.
    app.include_router(collector_router, prefix=API_PREFIX)
    if not settings.is_prod:
        # Письма с кодами наружу не выставляются: в проде маршрута просто нет,
        # он не появляется и в OpenAPI.
        app.include_router(dev_router, prefix=API_PREFIX)
    return app


app = create_app()
