"""Авторизация коллектора по сервисному токену — SPEC.md 5.3, 5.6.

Не сессия: у коллектора нет пользователя и нет браузера. `Authorization: Bearer <token>`,
где token — `COLLECTOR_TOKEN` из окружения.

Три решения, каждое из которых стоит дороже обычного, потому что за этой дверью лежит
единственный маршрут, отдающий пароль счёта наружу (`CLAUDE.md` §5).

1. **Отсутствующий и неверный токен неотличимы в ответе.** Один статус, один код, одно
   сообщение, ни одного заголовка про схему аутентификации. Разные ответы сказали бы
   подбирающему, что форма `Bearer …` принята, — то есть подтвердили бы, чем именно
   закрыта дверь. Отличать их надо не подбирающему, а тому, кто чинит коллектор,
   поэтому причина уходит в лог, а не в тело ответа.
2. **Сравнение постоянного времени.** `==` на строках выходит на первом несовпавшем
   байте; токен длинный и живёт годами.
3. **Незаполненный `COLLECTOR_TOKEN` закрывает маршрут, а не открывает.** В `local`
   секреты не обязательны (`check_production_secrets`), и без этой проверки пустое
   значение совпало бы с пустым `Bearer ` — пароли счетов отдавались бы кому угодно.
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings, is_secret_filled
from app.core.errors import ApiError
from app.core.logging import get_logger

log = get_logger(__name__)

BEARER_SCHEME = "bearer"

UNAUTHORIZED_CODE = "unauthorized"
UNAUTHORIZED_MESSAGE = "Требуется сервисный токен коллектора"

# Причины различает лог, а не ответ.
REASON_NOT_CONFIGURED = "collector_token_not_configured"
REASON_NO_HEADER = "no_bearer_token"
REASON_MISMATCH = "token_mismatch"


def _unauthorized() -> ApiError:
    return ApiError(UNAUTHORIZED_CODE, UNAUTHORIZED_MESSAGE, status_code=401)


def presented_token(request: Request) -> str | None:
    """Значение из `Authorization: Bearer …`. `None` — заголовка нет или он не Bearer."""
    header = request.headers.get("authorization")
    if header is None:
        return None
    scheme, separator, value = header.partition(" ")
    if not separator or scheme.lower() != BEARER_SCHEME:
        return None
    token = value.strip()
    return token or None


def token_matches(presented: str, expected: str) -> bool:
    """`compare_digest` по байтам: на `str` он требует ASCII и падает на кириллице в токене."""
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


async def require_collector_token(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> None:
    """Пропускает дальше только владельца `COLLECTOR_TOKEN`. Значение токена не логируется."""
    reason: str | None = None
    presented = presented_token(request)
    if not is_secret_filled(settings.collector_token):
        reason = REASON_NOT_CONFIGURED
    elif presented is None:
        reason = REASON_NO_HEADER
    elif not token_matches(presented, settings.collector_token.get_secret_value()):
        reason = REASON_MISMATCH
    if reason is None:
        return
    log.warning(
        "collector.auth_rejected", reason=reason, method=request.method, path=request.url.path
    )
    raise _unauthorized()


CollectorAuth = Depends(require_collector_token)
