"""structlog: один JSON-объект на строку в stdout, включая логи uvicorn."""

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Callable, Iterable
from functools import partial
from itertools import islice

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

# Ключи, значение которых не выводится никогда — даже если попало в событие по ошибке.
SECRET_EVENT_KEYS = frozenset(
    {
        "secret_key",
        "master_key",
        "master_key_previous",
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
        # Одноразовый код входа — секрет на время жизни; email — персональные данные,
        # в логах их держать сверх необходимого нельзя.
        "code",
        "otp",
        "otp_code",
        "verification_code",
        "email",
        # Envelope-шифрование credentials (S0-05): открытый пароль счёта, ключ данных
        # и оба слоя блоба. Блобы не секрет сами по себе, но в логе от них нет пользы.
        "credentials",
        "investor_password",
        "data_key",
        "wrapped_data_key",
        "ciphertext",
    }
)

REDACTED = "***"

# Пароль внутри connection string: postgresql://user:PASSWORD@host/db, redis://:PASSWORD@host.
_URL_CREDENTIALS = re.compile(r"(?P<prefix>[a-zA-Z][\w+.-]*://[^:/@\s]*:)(?P<password>[^@/\s]+)@")

# Короткие значения не скрабим: подстрока вроде "td" встречается в осмысленном тексте.
MIN_SCRUBBED_SECRET_LENGTH = 6

# Границы обхода вложенных значений. Процессор вызывается на каждой записи лога, а структура
# в аргументах бывает произвольной вплоть до циклической, поэтому обход ограничен по глубине,
# по ширине одной коллекции и по общему числу значений в записи (иначе ширина умножается
# на глубину). MIN_SCRUBBED_SECRET_LENGTH к этим лимитам отношения не имеет.
MAX_SCRUB_DEPTH = 4
MAX_SCRUB_ITEMS = 50
MAX_SCRUB_NODES = 500

# То, до чего обход не дошёл, в лог не попадает: непросмотренное значение могло бы вынести
# секрет. Маркер отличается от REDACTED — при разборе лога это разные причины.
UNSCANNED = "***(не проверено)"
# Ключ, под которым в dict уезжает счётчик непросмотренного остатка.
UNSCANNED_KEY = "***"

_known_secret_values: frozenset[str] = frozenset()


def register_secret_values(values: Iterable[str]) -> None:
    """Значения секретов из конфига — чтобы вырезать их из любого текста, а не только по ключу."""
    global _known_secret_values
    _known_secret_values = frozenset(
        value for value in values if len(value.strip()) >= MIN_SCRUBBED_SECRET_LENGTH
    )


def scrub_text(text: str) -> str:
    # Регексп квадратичен по длине строки: без совпадения он откатывается с каждой позиции,
    # а на 4 КБ это десятки миллисекунд. Без "://" совпадения быть не может — не запускаем.
    scrubbed = _URL_CREDENTIALS.sub(rf"\g<prefix>{REDACTED}@", text) if "://" in text else text
    for secret in _known_secret_values:
        if secret in scrubbed:
            scrubbed = scrubbed.replace(secret, REDACTED)
    return scrubbed


def _unscanned(count: int) -> str:
    return f"***(ещё {count}, не проверено)"


# Сентинел «значение не заменено, идём внутрь»: None и REDACTED — легальные замены.
_WALK: object = object()

# Обходчик получает ключ, под которым лежит значение; у элемента коллекции ключа нет — None.
# Внутрь коллекции под секретным ключом обход не идёт: она срезается целиком.
_Visit = Callable[[object | None, object], object]

# `exc_info` — служебный кортеж (type, value, tb), а не пользовательские данные. Обход
# пересобрал бы его, и при исчерпанном бюджете он выродился бы в однокортеж: structlog такой
# не распознаёт, но считает истинным — и молча подставляет окружающий sys.exc_info().
# Текст исключения чистит scrub_values уже после format_exc_info.
UNWALKED_EVENT_KEYS = frozenset({"exc_info"})


def _walk_record(event_dict: EventDict, visit: _Visit) -> EventDict:
    """Общий обход записи для обоих цензоров: и по именам ключей, и по тексту значений.

    Заходит внутрь dict/list/tuple — секрет приезжает и телом запроса, и в `details` ошибки
    валидации. Значения прочих типов отдаются как есть: их печатает через repr() скрабящий
    `default` JSON-рендерера, там же из них и вырезается секрет.

    Вложенные коллекции пересобираются, а не правятся на месте: объект принадлежит вызывающему
    коду, логирование не вправе его менять.
    """
    budget = MAX_SCRUB_NODES

    def walk(key: object | None, value: object, depth: int) -> object:
        nonlocal budget
        replacement = visit(key, value)
        if replacement is not _WALK:
            return replacement
        if not isinstance(value, dict | list | tuple):
            return value
        if depth >= MAX_SCRUB_DEPTH:
            return UNSCANNED
        visited = min(len(value), MAX_SCRUB_ITEMS, budget)
        budget -= visited
        skipped = len(value) - visited
        if isinstance(value, dict):
            walked = {k: walk(k, item, depth + 1) for k, item in islice(value.items(), visited)}
            if skipped:
                walked[UNSCANNED_KEY] = _unscanned(skipped)
            return walked
        items: list[object] = [walk(None, item, depth + 1) for item in islice(value, visited)]
        if skipped:
            items.append(_unscanned(skipped))
        return tuple(items) if isinstance(value, tuple) else items

    for key, value in event_dict.items():
        if key not in UNWALKED_EVENT_KEYS:
            event_dict[key] = walk(key, value, 0)
    return event_dict


def _scrub_leaf(_key: object | None, value: object) -> object:
    return scrub_text(value) if isinstance(value, str) else _WALK


def scrub_values(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    """Чистит ЗНАЧЕНИЯ, а не только ключи: traceback в поле `exception` содержит текст ошибки,
    а в нём — DSN с паролем. Идёт после format_exc_info, когда traceback уже строка."""
    return _walk_record(event_dict, _scrub_leaf)


def scrub_unserializable(value: object) -> str:
    """`default` для json.dumps: всё, что не JSON-тип, рендерер печатает через repr().

    Обход записи такие значения не трогает, а секрет в них — штатный случай: `error=exc`
    несёт DSN в тексте исключения, bytes и set — в repr своего содержимого.
    """
    return scrub_text(repr(value))


_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def _censor_secret_key(key: object | None, _value: object) -> object:
    if isinstance(key, str) and key.lower() in SECRET_EVENT_KEYS:
        return REDACTED
    return _WALK


def censor_secrets(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    """Последний рубеж: секрет, попавший в событие, заменяется на `***` — на любой глубине.
    Тело запроса и `details` ошибки валидации приходят структурой, а не плоским аргументом."""
    return _walk_record(event_dict, _censor_secret_key)


def _shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        censor_secrets,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        # Строго после format_exc_info: до него traceback ещё не текст.
        scrub_values,
    ]


def configure_logging(level: str = "INFO", secret_values: Iterable[str] = ()) -> None:
    """Идемпотентна: повторный вызов переустанавливает конфигурацию целиком."""
    register_secret_values(secret_values)
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
            # default передаётся сюда, а не в partial: JSONRenderer подставляет свой `default`
            # в kwargs вызова, а они перекрывают заданные в partial.
            structlog.processors.JSONRenderer(
                serializer=partial(json.dumps, ensure_ascii=False),
                default=scrub_unserializable,
            ),
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
