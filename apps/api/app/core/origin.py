"""Проверка заголовка `Origin` на мутирующих запросах — CSRF из SPEC.md 4.

Отдельный CSRF-токен не нужен: SPA и API живут на одном origin, cookie сессии —
`SameSite=Lax`. Проверка применяется ко всем мутирующим запросам приложения, а не
только к auth: любой будущий POST наследует её автоматически.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.errors import error_response
from app.core.logging import get_logger

log = get_logger(__name__)

# `SameSite=Lax` пропускает cookie только на них, поэтому проверять их незачем.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

FORBIDDEN_ORIGIN_CODE = "forbidden_origin"
FORBIDDEN_ORIGIN_MESSAGE = "Запрос отклонён: недопустимый источник"


def normalize_origin(value: str) -> str:
    """`http://host:5173/path` -> `http://host:5173`. Пустая строка, если не разбирается."""
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return ""
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}".lower()


def is_origin_allowed(origin: str, allowed: set[str]) -> bool:
    normalized = normalize_origin(origin)
    return bool(normalized) and normalized in allowed


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Отсутствующий `Origin` пропускается.

    Браузер ставит его на каждый мутирующий запрос, поэтому запрос без заголовка —
    не браузерный (коллектор, curl), и ambient-авторизации cookie у него нет.
    Требовать заголовок означало бы сломать коллектор ради угрозы, которой там нет.
    """

    def __init__(self, app: Callable[..., Awaitable[None]], app_url: str) -> None:
        super().__init__(app)
        self._app_origin = normalize_origin(app_url)

    def _allowed(self, request: Request) -> set[str]:
        # Собственный origin запроса: в проде фронт и API за одним прокси. Подменённый
        # Host здесь ничего не даёт — браузер ставит в Host настоящий адрес назначения.
        host = request.headers.get("host", "")
        own = normalize_origin(f"{request.url.scheme}://{host}") if host else ""
        return {value for value in (self._app_origin, own) if value}

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        origin = request.headers.get("origin")
        if (
            request.method not in SAFE_METHODS
            and origin is not None
            and not is_origin_allowed(origin, self._allowed(request))
        ):
            log.warning(
                "api.origin_rejected",
                method=request.method,
                path=request.url.path,
                origin=normalize_origin(origin),
            )
            return error_response(403, FORBIDDEN_ORIGIN_CODE, FORBIDDEN_ORIGIN_MESSAGE)
        return await call_next(request)
