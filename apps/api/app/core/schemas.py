"""Примитивы схем, общие для всех доменов — SPEC.md 5.1.

Здесь живут два решения о представлении чисел и времени наружу. Оба задаются один раз,
чтобы у второго домена не появилось второго написания: расхождение видно только на
фронте и только на нужных данных.

Время в API — ISO 8601 с `Z`. Pydantic по умолчанию печатает `+00:00`, и разница не
косметическая: `Date.parse` понимает оба написания, а вот `datetime.fromisoformat` до
3.11 и половина парсеров в тестах и скриптах — только одно из них. Написание задаётся
здесь один раз, чтобы у второго домена не появилось второе.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer, WithJsonSchema

UTC_SUFFIX = "Z"
_ISO_UTC_OFFSET = "+00:00"


def to_utc_z(value: datetime) -> str:
    """ISO 8601 в UTC с `Z`.

    Наивное время трактуется как UTC: все колонки времени в схеме — `timestamptz`
    (SPEC.md 3), поэтому наивное значение сюда попадает только из кода, который забыл
    таймзону, и молча сдвинуть его на смещение машины было бы хуже, чем принять за UTC.
    """
    moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat().replace(_ISO_UTC_OFFSET, UTC_SUFFIX)


# `WithJsonSchema` обязателен: `PlainSerializer(return_type=str)` описал бы поле как
# просто строку, и фронт получил бы `string` вместо `string(date-time)`.
UtcDatetime = Annotated[
    datetime,
    PlainSerializer(to_utc_z, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "date-time"}),
]


def to_decimal_string(value: Decimal) -> str:
    """Деньги, цены и объёмы уходят строкой, а не числом JSON.

    В JSON нет десятичного типа: число распаковывается в double, и `numeric(18,2)`
    теряет и точность на больших суммах, и масштаб — «10.50» превращается в 10.5.
    Строка сохраняет ровно то, что лежит в колонке, включая хвостовые нули, а разбор
    на фронте всё равно нужен: складывать деньги в double там тоже нельзя.
    """
    return str(value)


# Аннотация схемы обязательна по той же причине, что у `UtcDatetime`, только острее:
# pydantic описывает `Decimal` как `anyOf[number, string]`, и `make types` дал бы фронту
# `number | string` — тип, который заставляет проверять форму в каждом месте показа.
Money = Annotated[
    Decimal,
    PlainSerializer(to_decimal_string, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "description": "Десятичное число, numeric(18,2)"}),
]

Quantity = Annotated[
    Decimal,
    PlainSerializer(to_decimal_string, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "description": "Десятичное число, numeric(18,8)"}),
]
