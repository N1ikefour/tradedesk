"""Курсор списка позиций — SPEC.md 5.1.

**Ни одно из пяти полей сортировки не уникально.** `close_time`, `open_time`, `net_pnl`,
`symbol_norm`, `duration_seconds` — у любого из них две строки легко совпадают: две сделки
закрылись в одну секунду, две дали ровно ноль, две на одном символе. Курсор, хранящий
только значение поля, на такой границе либо перепрыгивает строку, либо показывает её
дважды, и заметить это невозможно: человек просто не увидит одну свою сделку и не узнает,
что не увидел.

Поэтому ключ курсора **составной**: `(значение поля, positions.id)`. `id` — первичный ключ,
он уникален по построению, поэтому пара уникальна всегда, а порядок по ней — полный. Тем же
составным ключом идёт и `ORDER BY`, иначе сравнение в `WHERE` описывало бы не тот порядок,
в котором строки выдаются (сборка обоих — `service._keyset`).

Пустое значение ключа — часть протокола, а не особый случай. `close_time` и
`duration_seconds` у открытых позиций `NULL`, открытые позиции всегда идут первой группой
(см. `service._keyset`), и курсор обязан уметь указывать внутрь этой группы: `value =
None` означает «строка без значения, продолжаем с неё».

Что курсор **не** несёт — фильтры. Сменить фильтр, оставив курсор, — определённое действие:
получишь хвост нового списка от той же точки ключа. Сменить сортировку — нет: ключ начинает
означать другое, поэтому поле и направление в курсоре сверяются с запросом, и расхождение
роняет запрос, а не выдаёт молча съехавшую страницу.

Наружу нечитаемый курсор уходит обычной ошибкой валидации параметра запроса — `400
validation_error` с `details.fields["query.cursor"]` (SPEC.md 5.1), потому что разбирается
он на границе, в `schemas.PositionsQuery`, вместе с остальными параметрами. Отдельного
доменного кода у него нет намеренно: у всех способов испортить курсор одно и то же
лекарство — открыть список заново, — и разные коды обещали бы разные действия, которых нет.
"""

from __future__ import annotations

import binascii
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Final, Literal, get_args
from uuid import UUID

SortField = Literal["close_time", "open_time", "net_pnl", "symbol_norm", "duration_seconds"]
SORT_FIELDS: Final[tuple[str, ...]] = get_args(SortField)

# Значение ключа сортировки в том виде, в каком его отдаёт строка таблицы. Перечислено
# союзом, а не `object`: сериализация разбирает его по типу, и `object` прятал бы от mypy
# ровно те ветки, ради которых разбор написан.
CursorValue = datetime | Decimal | int | str

SortDirection = Literal["asc", "desc"]
SORT_DIRECTIONS: Final[tuple[str, ...]] = get_args(SortDirection)

DEFAULT_SORT = "close_time:desc"
SORT_SEPARATOR = ":"

# Поля, у которых значение может отсутствовать: у открытой позиции нет ни времени
# закрытия, ни длительности.
NULLABLE_SORT_FIELDS: Final[frozenset[str]] = frozenset({"close_time", "duration_seconds"})

# Один текст на все поломки курсора: для клиента это непрозрачный токен, и подробность
# разбора («не base64», «не та сортировка») описывала бы его устройство, ничего не меняя
# в действиях клиента. Причина остаётся в сообщении исключения — его читают тесты.
INVALID_CURSOR_MESSAGE = "Курсор страницы недействителен. Откройте список заново"

SORT_ERROR = (
    "Сортировка задаётся как «поле:направление», поле — одно из "
    + ", ".join(SORT_FIELDS)
    + "; направление — asc или desc"
)

# Ключи короткие: курсор уезжает в URL, а туда же уедут все фильтры журнала (S2-06).
_FIELD_KEY = "s"
_DIRECTION_KEY = "d"
_VALUE_KEY = "v"
_ID_KEY = "i"
_KEYS = frozenset({_FIELD_KEY, _DIRECTION_KEY, _VALUE_KEY, _ID_KEY})

# Значение всегда строка, даже целое: одно правило разбора вместо разбора по типу JSON,
# в котором `1` и `"1"` разъезжаются молча.
_MAX_VALUE_LENGTH = 64


class InvalidCursorError(ValueError):
    """Курсор нечитаем, подделан или собран под другую сортировку."""


@dataclass(frozen=True, slots=True)
class Sort:
    """Разобранный `?sort=поле:направление`."""

    field: SortField
    direction: SortDirection

    @property
    def descending(self) -> bool:
        return self.direction == "desc"

    @property
    def nullable(self) -> bool:
        return self.field in NULLABLE_SORT_FIELDS

    def __str__(self) -> str:
        return f"{self.field}{SORT_SEPARATOR}{self.direction}"


@dataclass(frozen=True, slots=True)
class Cursor:
    """Точка, после которой начинается следующая страница.

    `value is None` — это не «значения нет», а «у той строки поле было пусто»: позиция
    внутри группы открытых позиций, которая идёт первой.
    """

    sort: Sort
    value: CursorValue | None
    position_id: UUID


def parse_sort(raw: str) -> Sort:
    """`close_time:desc` -> `Sort`. Всё, что не из словаря, — ошибка, а не «по умолчанию».

    Молчаливый откат к сортировке по умолчанию был бы хуже ошибки: список выглядел бы
    рабочим, просто отсортированным не по тому, что попросили.
    """
    field, separator, direction = raw.partition(SORT_SEPARATOR)
    if not separator or field not in SORT_FIELDS or direction not in SORT_DIRECTIONS:
        raise ValueError(SORT_ERROR)
    return Sort(field=field, direction=direction)  # type: ignore[arg-type]


def encode_cursor(sort: Sort, value: CursorValue | None, position_id: UUID) -> str:
    """Курсор строки: её значение ключа сортировки и её `id`.

    Не подпись и не секрет — подделать его можно, но подделка не даёт ничего: скоупинг по
    владельцу стоит на `account_ids`, а не на курсоре, и чужую строку в ответ он не
    приносит. base64url — чтобы значение пережило URL без экранирования.
    """
    payload = {
        _FIELD_KEY: sort.field,
        _DIRECTION_KEY: sort.direction,
        _VALUE_KEY: None if value is None else _serialize(sort.field, value),
        _ID_KEY: str(position_id),
    }
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(raw: str, sort: Sort) -> Cursor:
    """Курсор из запроса. Любая неисправность — `InvalidCursorError`, без частичного разбора."""
    payload = _payload(raw)
    if payload.get(_FIELD_KEY) != sort.field or payload.get(_DIRECTION_KEY) != sort.direction:
        raise InvalidCursorError("курсор собран под другую сортировку")

    encoded = payload.get(_VALUE_KEY)
    if encoded is None and not sort.nullable:
        # У `open_time`, `net_pnl` и `symbol_norm` колонка not null: пустое значение в
        # курсоре по такому полю не могло взяться из ответа этого API.
        raise InvalidCursorError("пустое значение ключа у поля, которое не бывает пустым")
    if encoded is not None and not isinstance(encoded, str):
        raise InvalidCursorError("значение ключа не строка")
    if isinstance(encoded, str) and len(encoded) > _MAX_VALUE_LENGTH:
        raise InvalidCursorError("значение ключа длиннее допустимого")

    identifier = payload.get(_ID_KEY)
    if not isinstance(identifier, str):
        raise InvalidCursorError("идентификатор строки отсутствует")
    try:
        position_id = UUID(identifier)
    except ValueError as error:
        raise InvalidCursorError("идентификатор строки не UUID") from error

    value = None if encoded is None else _deserialize(sort.field, encoded)
    return Cursor(sort=sort, value=value, position_id=position_id)


def _payload(raw: str) -> dict[str, object]:
    if not raw:
        raise InvalidCursorError("пустой курсор")
    # Паддинг снят при кодировании: b64decode без него падает, а длина восстанавливается
    # однозначно.
    padded = raw + "=" * (-len(raw) % 4)
    try:
        decoded = json.loads(urlsafe_b64decode(padded.encode("ascii")))
    except (UnicodeEncodeError, binascii.Error, ValueError) as error:
        raise InvalidCursorError("курсор не разбирается") from error
    if not isinstance(decoded, dict) or not _KEYS.issuperset(decoded):
        raise InvalidCursorError("курсор не той формы")
    return decoded


def _serialize(field: str, value: CursorValue) -> str:
    if field in ("close_time", "open_time"):
        if not isinstance(value, datetime):
            raise TypeError(f"{field}: ожидалось время, получено {type(value).__name__}")
        # Наивное время сюда попасть не должно (все колонки — timestamptz), но если
        # попало — считаем его UTC, как `core.schemas.to_utc_z`, а не зоной машины.
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).isoformat()
    if field == "net_pnl":
        if not isinstance(value, Decimal):
            raise TypeError(f"{field}: ожидалось Decimal, получено {type(value).__name__}")
        return str(value)
    if field == "duration_seconds":
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError(f"{field}: ожидалось целое, получено {type(value).__name__}")
        return str(value)
    if not isinstance(value, str):
        raise TypeError(f"{field}: ожидалась строка, получено {type(value).__name__}")
    return value


def _deserialize(field: str, encoded: str) -> CursorValue:
    if field in ("close_time", "open_time"):
        try:
            moment = datetime.fromisoformat(encoded)
        except ValueError as error:
            raise InvalidCursorError("значение ключа не время") from error
        return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    if field == "net_pnl":
        try:
            amount = Decimal(encoded)
        except (InvalidOperation, ValueError) as error:
            raise InvalidCursorError("значение ключа не число") from error
        # NaN сравнивается со всем подряд неверно, а в numeric-колонку он и не попадёт.
        if not amount.is_finite():
            raise InvalidCursorError("значение ключа не конечное число")
        return amount
    if field == "duration_seconds":
        try:
            return int(encoded)
        except ValueError as error:
            raise InvalidCursorError("значение ключа не целое") from error
    return encoded
