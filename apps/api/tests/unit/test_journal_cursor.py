"""Курсор списка позиций — S2-01.

Курсор — единственное место, где ошибка не видна ни в ответе, ни в логе: страница
выглядит нормальной, просто одной строки в ней нет. Поэтому здесь проверяется не
«разбирается ли токен», а два его свойства:

* **обратимость** — то, что закодировали, читается назад тем же значением и тем же
  типом (`Decimal` не должен по дороге стать `float`, а время — потерять зону);
* **закрытость** — любая порча, подделка и несовпадение с сортировкой запроса дают
  `InvalidCursorError`, а не частично разобранный курсор.

Полнота выдачи на неуникальных ключах доказывается не здесь, а в
`tests/integration/test_journal.py`: у неё нужен настоящий `ORDER BY`.
"""

from __future__ import annotations

import json
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.domains.journal.cursor import (
    DEFAULT_SORT,
    NULLABLE_SORT_FIELDS,
    SORT_DIRECTIONS,
    SORT_FIELDS,
    CursorValue,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
    parse_sort,
)

SPEC_SORT_FIELDS = ("close_time", "open_time", "net_pnl", "symbol_norm", "duration_seconds")

MOMENT = datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC)

VALUES: dict[str, CursorValue] = {
    "close_time": MOMENT,
    "open_time": MOMENT,
    "net_pnl": Decimal("-10.50"),
    "symbol_norm": "EURUSD",
    "duration_seconds": 3600,
}


def _token(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def test_sort_fields_match_the_spec() -> None:
    """SPEC.md 5.4 перечисляет поля сортировки поимённо; список продублирован намеренно."""
    assert set(SORT_FIELDS) == set(SPEC_SORT_FIELDS)
    assert set(SORT_DIRECTIONS) == {"asc", "desc"}
    assert DEFAULT_SORT == "close_time:desc"


def test_only_close_time_and_duration_can_be_empty() -> None:
    """Остальные три колонки `not null` (миграция b07a46275bbc) — пустыми они не бывают."""
    assert {"close_time", "duration_seconds"} == NULLABLE_SORT_FIELDS


@pytest.mark.parametrize("field", SPEC_SORT_FIELDS)
@pytest.mark.parametrize("direction", ("asc", "desc"))
def test_roundtrip_keeps_value_and_type(field: str, direction: str) -> None:
    sort = parse_sort(f"{field}:{direction}")
    position_id = uuid4()

    decoded = decode_cursor(encode_cursor(sort, VALUES[field], position_id), sort)

    assert decoded.sort == sort
    assert decoded.position_id == position_id
    assert decoded.value == VALUES[field]
    assert type(decoded.value) is type(VALUES[field])


def test_decimal_keeps_its_scale() -> None:
    """`10.50` и `10.5` в numeric равны, но курсор обязан вернуть ровно то, что записал."""
    sort = parse_sort("net_pnl:desc")

    decoded = decode_cursor(encode_cursor(sort, Decimal("10.50"), uuid4()), sort)

    assert str(decoded.value) == "10.50"


def test_time_from_another_zone_is_stored_as_utc() -> None:
    """Все колонки времени — timestamptz; в курсоре момент один, написание одно."""
    sort = parse_sort("close_time:desc")
    moscow = MOMENT.astimezone(timezone(timedelta(hours=3)))

    decoded = decode_cursor(encode_cursor(sort, moscow, uuid4()), sort)

    assert decoded.value == MOMENT


@pytest.mark.parametrize("field", sorted(NULLABLE_SORT_FIELDS))
def test_empty_value_is_part_of_the_protocol(field: str) -> None:
    """`value is None` — «строка без значения», а не «курсора нет»: у открытых позиций так."""
    sort = parse_sort(f"{field}:desc")
    position_id = uuid4()

    decoded = decode_cursor(encode_cursor(sort, None, position_id), sort)

    assert decoded.value is None
    assert decoded.position_id == position_id


@pytest.mark.parametrize("field", ("open_time", "net_pnl", "symbol_norm"))
def test_empty_value_on_a_not_null_field_is_rejected(field: str) -> None:
    """Такой курсор не мог прийти из ответа этого API — значит он подделан или испорчен.

    Токен собирается вручную: `encode_cursor` такой пары не выдаёт, а проверять надо
    именно то, чего наш собственный кодировщик не производит.
    """
    token = _token({"s": field, "d": "asc", "v": None, "i": str(uuid4())})

    with pytest.raises(InvalidCursorError):
        decode_cursor(token, parse_sort(f"{field}:asc"))


def test_token_survives_a_url() -> None:
    """Курсор уезжает в query — там же, где живут все фильтры журнала (S2-06)."""
    token = encode_cursor(parse_sort(DEFAULT_SORT), MOMENT, uuid4())

    assert set(token) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


# --- закрытость ---------------------------------------------------------------


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param("", id="пусто"),
        pytest.param("!!!", id="не base64"),
        pytest.param(urlsafe_b64encode(b"not json").decode().rstrip("="), id="не json"),
        pytest.param(_token({"s": "close_time"}), id="без id и значения"),
        pytest.param(_token(["close_time", "desc"]), id="не объект"),  # type: ignore[arg-type]
        pytest.param(
            _token({"s": "close_time", "d": "desc", "v": "x", "i": "не-uuid"}), id="id не uuid"
        ),
        pytest.param(
            _token({"s": "close_time", "d": "desc", "v": "не-время", "i": str(uuid4())}),
            id="значение не время",
        ),
        pytest.param(
            _token({"s": "close_time", "d": "desc", "v": 12345, "i": str(uuid4())}),
            id="значение не строка",
        ),
        pytest.param(
            _token({"s": "close_time", "d": "desc", "v": "x" * 65, "i": str(uuid4())}),
            id="значение длиннее предела",
        ),
        pytest.param(
            _token({"s": "close_time", "d": "desc", "v": None, "i": str(uuid4()), "x": 1}),
            id="лишний ключ",
        ),
    ],
)
def test_broken_cursor_raises(broken: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(broken, parse_sort("close_time:desc"))


@pytest.mark.parametrize("other", ["close_time:asc", "net_pnl:desc", "open_time:desc"])
def test_cursor_built_for_another_sort_is_rejected(other: str) -> None:
    """Под другим порядком тот же ключ указывает на другое место списка."""
    sort = parse_sort("close_time:desc")
    token = encode_cursor(sort, MOMENT, uuid4())

    with pytest.raises(InvalidCursorError):
        decode_cursor(token, parse_sort(other))


@pytest.mark.parametrize("bogus", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_amount_is_rejected(bogus: str) -> None:
    """NaN сравнивается со всем подряд неверно, а в numeric-колонку он и не попадёт."""
    token = _token({"s": "net_pnl", "d": "desc", "v": bogus, "i": str(uuid4())})

    with pytest.raises(InvalidCursorError):
        decode_cursor(token, parse_sort("net_pnl:desc"))


def test_duration_must_be_an_integer() -> None:
    token = _token({"s": "duration_seconds", "d": "asc", "v": "3600.5", "i": str(uuid4())})

    with pytest.raises(InvalidCursorError):
        decode_cursor(token, parse_sort("duration_seconds:asc"))


@pytest.mark.parametrize(
    "raw", ["", "close_time", "close_time:", ":desc", "close_time:вниз", "account_id:desc"]
)
def test_unknown_sort_is_not_silently_replaced_by_the_default(raw: str) -> None:
    """Молчаливый откат к сортировке по умолчанию хуже ошибки: список выглядел бы рабочим."""
    with pytest.raises(ValueError):
        parse_sort(raw)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("close_time", "2026-09-01"),
        ("net_pnl", 10),
        ("duration_seconds", True),
        ("symbol_norm", 5),
    ],
)
def test_encoding_a_wrong_type_is_a_programming_error(field: str, value: object) -> None:
    """`TypeError`, а не `InvalidCursorError`: испорчен не ввод клиента, а наш собственный код."""
    with pytest.raises(TypeError):
        encode_cursor(parse_sort(f"{field}:asc"), value, uuid4())  # type: ignore[arg-type]


def test_sort_reads_back_as_the_query_wrote_it() -> None:
    sort = parse_sort("net_pnl:asc")

    assert str(sort) == "net_pnl:asc"
    assert sort.descending is False
    assert sort.nullable is False
    assert parse_sort("close_time:desc").nullable is True


def test_position_id_is_the_full_uuid() -> None:
    """Обрезанный идентификатор означал бы другую строку — а курсор им и отличает строки."""
    position_id = UUID("00000000-0000-0000-0000-000000000001")
    sort = parse_sort("symbol_norm:asc")

    decoded = decode_cursor(encode_cursor(sort, "EURUSD", position_id), sort)

    assert decoded.position_id == position_id
