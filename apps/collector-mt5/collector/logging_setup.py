"""structlog в файл с ротацией — `SPEC.md` §8.2, пункт 3.

В логах коллектора **никогда** нет сервисного токена (`CLAUDE.md` §5). Держится это не на
внимательности автора: в цепочку процессоров встроен скраб, который вырезает известные
секреты из любого значения события, как бы оно туда ни попало.

Реестр (`register_secret`), а не кортеж, собранный в `setup_logging`: скраб читает список
на каждом событии. Изначально живым он был потому, что пароль счёта приходил позже старта
— в ответе assignments; с `X-66`/`T-07` пароля у коллектора нет вовсе, и сегодня в реестре
живёт один `COLLECTOR_TOKEN`. Реестр остаётся живым намеренно: следующий секрет, который
появится в процессе после первой строки лога, не должен требовать переделки скраба.

Файл лога один — `logs/collector.log`, как и говорит `SPEC.md` §8.2 п. 3. Файлы на счёт
были нужны, пока счёт вёл отдельный процесс (`S1-09`): `RotatingFileHandler` на Windows
переименовывает файл при перевороте без блокировки между процессами. С `X-66` процесс
один — один терминал на машину, один открытый счёт, — и делить файл не с кем.
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

LOG_NAME: Final = "collector.log"

SECRET_PLACEHOLDER: Final = "***"

# Значения короче этого не вырезаются: подстрока в два символа встретится в любом тексте
# и превратила бы лог в решето из звёздочек. Сервисный токен заведомо длиннее.
MIN_SCRUBBED_SECRET_LENGTH: Final = 8


# Секреты процесса. Реестр, а не аргумент `setup_logging`: секрет, появившийся в процессе
# после первой строки лога, обязан попасть под скраб, не переделывая проводку.
_SECRETS: set[str] = set()


def register_secret(value: str) -> None:
    """Внести значение в скраб. Короткие не берём — они превратили бы лог в решето."""
    if len(value) >= MIN_SCRUBBED_SECRET_LENGTH:
        _SECRETS.add(value)


def known_secrets() -> tuple[str, ...]:
    """Что скраб вырезает прямо сейчас. Порядок неважен, содержимое — да."""
    return tuple(_SECRETS)


def forget_secrets() -> None:
    """Забыть всё. Нужно тестам; в бою процесс живёт с одним набором секретов."""
    _SECRETS.clear()


def scrub_text(text: str, secrets: Iterable[str]) -> str:
    """Убрать известные секреты из строки."""
    cleaned = text
    for secret in secrets:
        if len(secret) >= MIN_SCRUBBED_SECRET_LENGTH and secret in cleaned:
            cleaned = cleaned.replace(secret, SECRET_PLACEHOLDER)
    return cleaned


def scrub_event(event: dict[str, Any], secrets: Iterable[str]) -> dict[str, Any]:
    """Скраб всего события: и ключей верхнего уровня, и вложенных строк.

    Обходятся значения, а не имена полей. Секрет, попавший в текст исключения от сторонней
    библиотеки, — реальный путь утечки, и ловится он только по значению: имя поля там
    будет чужое или его не будет вовсе.
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
    """Поднять structlog: файл с ротацией плюс консоль, со скрабом в обеих.

    Скраб читает реестр на каждом событии, а не запоминает список при старте
    (`register_secret`).
    """
    log_file.parent.mkdir(parents=True, exist_ok=True)
    # Реестр пополняется, а не переписывается: секрет, ставший известным раньше вызова, не
    # имеет права перестать быть секретом от того, что логи подняли повторно. Забывает всё
    # только `forget_secrets` — она нужна тестам.
    for secret in secrets:
        register_secret(secret)

    def scrubbing(
        _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        return scrub_event(dict(event_dict), known_secrets())

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
