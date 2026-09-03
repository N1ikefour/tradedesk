"""structlog: один JSON-объект на строку в stdout, включая логи uvicorn."""

from __future__ import annotations

import json
import logging
import sys
from functools import partial

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

# Ключи, значение которых не выводится никогда — даже если попало в событие по ошибке.
SECRET_EVENT_KEYS = frozenset(
    {
        "secret_key",
        "master_key",
        "otp_pepper",
        "collector_token",
        "database_url",
        "redis_url",
        "resend_api_key",
        "s3_secret_key",
        "s3_access_key",
        "sentry_dsn",
        "password",
        "token",
        "authorization",
        "api_key",
    }
)

REDACTED = "***"

_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def censor_secrets(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    """Последний рубеж: секрет, попавший в событие, заменяется на `***`."""
    for key in list(event_dict):
        if key.lower() in SECRET_EVENT_KEYS:
            event_dict[key] = REDACTED
    return event_dict


def _shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        censor_secrets,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]


def configure_logging(level: str = "INFO") -> None:
    """Идемпотентна: повторный вызов переустанавливает конфигурацию целиком."""
    shared = _shared_processors()

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        # foreign_pre_chain обрабатывает записи из stdlib logging (uvicorn, sqlalchemy).
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            # ensure_ascii=False: сообщения на русском читаются глазами, а не как \uXXXX.
            structlog.processors.JSONRenderer(serializer=partial(json.dumps, ensure_ascii=False)),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)
