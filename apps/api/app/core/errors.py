"""Единый формат ошибок API — SPEC.md 5.1.

{"error": {"code": "snake_case", "message": "по-русски", "details": {}}}
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ExceptionHandler

from app.core.db import describe_database_error
from app.core.logging import get_logger

log = get_logger(__name__)

# Стабильный словарь: HTTP-код -> код ошибки. Коды берутся из SPEC.md 5.1.
CODE_BY_STATUS: dict[int, str] = {
    400: "validation_error",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    415: "unsupported_media_type",
    422: "unprocessable_entity",
    429: "rate_limited",
    500: "internal_error",
}

MESSAGE_BY_STATUS: dict[int, str] = {
    400: "Ошибка валидации запроса",
    401: "Требуется аутентификация",
    403: "Доступ запрещён",
    404: "Ресурс не найден",
    405: "Метод не поддерживается",
    409: "Конфликт состояния",
    415: "Неподдерживаемый тип содержимого",
    422: "Запрос не может быть выполнен",
    429: "Слишком много запросов",
    500: "Внутренняя ошибка сервера",
}

FALLBACK_CODE = "internal_error"
FALLBACK_MESSAGE = "Внутренняя ошибка сервера"


class ApiError(Exception):
    """Ошибка бизнес-уровня. Код и сообщение задаёт домен, маппинг на HTTP — здесь."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        # Часть кодов описана не только телом: 429 несёт стандартный `Retry-After`.
        self.headers = headers or {}


def error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_payload(code, message, details),
        headers=headers,
    )


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    status = exc.status_code
    code = CODE_BY_STATUS.get(status, FALLBACK_CODE)
    message = MESSAGE_BY_STATUS.get(status, FALLBACK_MESSAGE)
    # Стандартный detail Starlette («Not Found») — текст фреймворка, а не наше сообщение.
    if isinstance(exc.detail, str) and exc.detail and exc.detail != _standard_phrase(status):
        message = exc.detail
    return error_response(status, code, message)


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 от FastAPI приводится к 400 `validation_error` из SPEC.md 5.1."""
    fields: dict[str, str] = {}
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        # Только msg: `input` и `ctx` содержат присланные значения, в т.ч. потенциально секреты.
        fields[location] = str(error["msg"])
    return error_response(400, "validation_error", MESSAGE_BY_STATUS[400], {"fields": fields})


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Наружу — ничего, кроме кода: текст исключения может содержать секреты.

    В лог — тоже. Ошибка БД несёт содержимое упавшей строки и в тексте SQLAlchemy,
    и в `DETAIL` самого Postgres, поэтому вместо traceback печатается структурный
    портрет из `describe_database_error`. Для остальных исключений traceback остаётся:
    без него причина 500 не находится.
    """
    database = describe_database_error(exc)
    log.error(
        "api.unhandled_exception",
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
        exc_info=database is None,
        **(database or {}),
    )
    return error_response(500, FALLBACK_CODE, FALLBACK_MESSAGE)


def _standard_phrase(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return ""


def register_error_handlers(app: FastAPI) -> None:
    # cast: Starlette типизирует обработчик как (Request, Exception), сузить его нельзя.
    app.add_exception_handler(ApiError, cast(ExceptionHandler, api_error_handler))
    app.add_exception_handler(
        RequestValidationError, cast(ExceptionHandler, validation_error_handler)
    )
    app.add_exception_handler(
        StarletteHTTPException, cast(ExceptionHandler, http_exception_handler)
    )
    app.add_exception_handler(Exception, cast(ExceptionHandler, unhandled_exception_handler))
