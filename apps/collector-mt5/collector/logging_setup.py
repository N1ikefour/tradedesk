"""structlog в файл с ротацией — `SPEC.md` §8.2, пункт 3.

В логах коллектора **никогда** нет пароля счёта и сервисного токена (`CLAUDE.md` §5).
Держится это не на внимательности автора: в цепочку процессоров встроен скраб, который
вырезает известные секреты из любого значения события, как бы оно туда ни попало.
Проверяется тестом, который кладёт секрет под безобидным именем поля.

⚠️ Файл лога — **на счёт**, а не один на всех, хотя §8.2 называет `logs/collector.log`.
Причина в `S1-09`: один терминал = один дочерний процесс, а `RotatingFileHandler` на
Windows переименовывает файл при перевороте и делает это без блокировки между
процессами — два процесса на одном файле теряют записи ровно в момент ротации.
Менеджеру процессов имя из спеки остаётся.
"""

from __future__ import annotations

import logging
import logging.handlers
from collections.abc import Iterable, MutableMapping
from pathlib import Path
from typing import Any, Final

import structlog

MAX_LOG_BYTES: Final = 5 * 1024 * 1024
LOG_BACKUP_COUNT: Final = 5

MANAGER_LOG_NAME: Final = "collector.log"

SECRET_PLACEHOLDER: Final = "***"

# Значения короче этого не вырезаются: подстрока в два символа встретится в любом тексте
# и превратила бы лог в решето из звёздочек. Токен и пароль счёта заведомо длиннее.
MIN_SCRUBBED_SECRET_LENGTH: Final = 8


def account_log_name(account_id: str) -> str:
    """Имя файла лога процесса счёта. Идентификатор — UUID, посторонних символов в нём нет."""
    safe = "".join(char for char in account_id if char.isalnum() or char in "-_")
    return f"account-{safe or 'unknown'}.log"


def scrub_text(text: str, secrets: Iterable[str]) -> str:
    """Убрать известные секреты из строки."""
    cleaned = text
    for secret in secrets:
        if len(secret) >= MIN_SCRUBBED_SECRET_LENGTH and secret in cleaned:
            cleaned = cleaned.replace(secret, SECRET_PLACEHOLDER)
    return cleaned


def scrub_event(event: dict[str, Any], secrets: Iterable[str]) -> dict[str, Any]:
    """Скраб всего события: и ключей верхнего уровня, и вложенных строк.

    Обходятся значения, а не имена полей. Поле с честным именем `password` в коде
    коллектора не появляется вовсе, а вот пароль, попавший в текст исключения от
    сторонней библиотеки, — реальный путь утечки, и ловится он только по значению.
    """
    kept = tuple(secret for secret in secrets if len(secret) >= MIN_SCRUBBED_SECRET_LENGTH)
    if not kept:
        return event
    return {key: _scrub_value(value, kept) for key, value in event.items()}


def _scrub_value(value: Any, secrets: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        return scrub_text(value, secrets)
    if isinstance(value, dict):
        return {key: _scrub_value(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_scrub_value(item, secrets) for item in value)
    return value


def setup_logging(*, log_file: Path, level: str, secrets: Iterable[str]) -> None:
    """Поднять structlog: файл с ротацией плюс консоль, со скрабом в обеих."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    kept = tuple(secrets)

    def scrubbing(
        _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        return scrub_event(dict(event_dict), kept)

    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(
            log_file, maxBytes=MAX_LOG_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
        ),
        logging.StreamHandler(),
    ]
    logging.basicConfig(level=level, format="%(message)s", handlers=handlers, force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Скраб стоит последним перед рендером намеренно: `format_exc_info`
            # разворачивает трейсбек в строку, и до него вырезать из неё нечего.
            scrubbing,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
