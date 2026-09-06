"""Границы `GET /journal/positions` — S2-01.

Здесь проверяется то, что должно упасть **до** запроса к базе: валидация фильтров
(`CLAUDE.md` §5 — валидация pydantic на границе один раз) и два вычисляемых поля ответа,
`result` и `notes_preview`.

Что фильтры действительно фильтруют — в `tests/integration/test_journal.py`: на живом SQL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.domains.ingest import models as ingest_models
from app.domains.journal.cursor import encode_cursor, parse_sort
from app.domains.journal.schemas import (
    DEFAULT_LIMIT,
    MAX_ACCOUNT_IDS,
    MAX_LIMIT,
    MAX_SEARCH_LENGTH,
    MAX_SYMBOL_LENGTH,
    MAX_TAG_LENGTH,
    MAX_TAGS,
    NOTES_PREVIEW_LENGTH,
    PositionsQuery,
    notes_preview,
    position_result,
)

MOMENT = datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC)


def query(**values: Any) -> PositionsQuery:
    return PositionsQuery.model_validate(values)


def _position(**overrides: Any) -> ingest_models.Position:
    position = ingest_models.Position()
    position.status = "closed"
    position.net_pnl = Decimal("0")
    for name, value in overrides.items():
        setattr(position, name, value)
    return position


# --- умолчания ----------------------------------------------------------------


def test_defaults_match_the_spec() -> None:
    """Журнал открывают, чтобы увидеть, чем кончился сегодняшний день."""
    parsed = query()

    assert parsed.sort == "close_time:desc"
    assert parsed.limit == DEFAULT_LIMIT
    assert parsed.cursor is None
    assert parsed.account_id_list == []
    assert parsed.tag_list == []
    assert parsed.sort_key == parse_sort("close_time:desc")
    assert parsed.cursor_key is None


def test_unknown_parameter_is_refused() -> None:
    """Опечатка в имени фильтра иначе молча вернула бы нефильтрованный список."""
    with pytest.raises(ValidationError):
        query(symbols="EURUSD")


@pytest.mark.parametrize("limit", [0, -1, MAX_LIMIT + 1])
def test_limit_is_bounded(limit: int) -> None:
    with pytest.raises(ValidationError):
        query(limit=limit)


def test_limit_bounds_are_inclusive() -> None:
    assert query(limit=1).limit == 1
    assert query(limit=MAX_LIMIT).limit == MAX_LIMIT


# --- период -------------------------------------------------------------------


@pytest.mark.parametrize("name", ["from", "to"])
def test_naive_time_is_refused(name: str) -> None:
    """Наивное время — не «UTC по умолчанию», а незаданный вопрос, чей это день."""
    with pytest.raises(ValidationError):
        query(**{name: "2026-09-01T00:00:00"})


def test_aware_time_is_accepted_in_any_zone() -> None:
    parsed = query(**{"from": "2026-09-01T15:00:00+03:00"})

    assert parsed.date_from == datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-09-02T00:00:00Z", "2026-09-01T00:00:00Z"),
        ("2026-09-01T00:00:00Z", "2026-09-01T00:00:00Z"),
    ],
)
def test_empty_or_reversed_period_is_refused(start: str, end: str) -> None:
    """Пустой список в ответ на `from >= to` человек читает как «сделок нет»."""
    with pytest.raises(ValidationError):
        query(**{"from": start, "to": end})


# --- счета, теги, символ, поиск -----------------------------------------------


def test_account_ids_are_parsed_and_kept_in_order() -> None:
    first, second = uuid4(), uuid4()

    parsed = query(account_ids=f" {first} , {second} ")

    assert parsed.account_id_list == [first, second]


@pytest.mark.parametrize("raw", ["не-uuid", f"{uuid4()},мусор"])
def test_broken_account_ids_are_refused_at_the_boundary(raw: str) -> None:
    """Разбор на границе даёт 400; разбор в свойстве дал бы 500 на том же вводе."""
    with pytest.raises(ValidationError):
        query(account_ids=raw)


def test_too_many_account_ids_are_refused() -> None:
    with pytest.raises(ValidationError):
        query(account_ids=",".join(str(uuid4()) for _ in range(MAX_ACCOUNT_IDS + 1)))


def test_empty_account_ids_mean_all_unarchived() -> None:
    assert query(account_ids="").account_id_list == []
    assert query(account_ids=" , ").account_id_list == []


def test_tags_are_split_and_trimmed() -> None:
    assert query(tags=" news , breakout ").tag_list == ["news", "breakout"]


@pytest.mark.parametrize(
    "tags",
    [
        ",".join(f"t{index}" for index in range(MAX_TAGS + 1)),
        "x" * (MAX_TAG_LENGTH + 1),
    ],
)
def test_oversized_tag_filter_is_refused(tags: str) -> None:
    with pytest.raises(ValidationError):
        query(tags=tags)


def test_symbol_is_upper_cased_for_the_indexed_column() -> None:
    """S1-07 кладёт в `symbol_norm` верхний регистр; сравнение идёт по колонке, не по upper()."""
    assert query(symbol=" xauusd ").symbol == "XAUUSD"


def test_blank_symbol_and_search_become_absent() -> None:
    """Пустая строка из формы — «фильтр не задан», а не «символ пустой»."""
    assert query(symbol="   ").symbol is None
    assert query(q="  ").q is None


@pytest.mark.parametrize(
    ("field", "value"),
    [("symbol", "X" * (MAX_SYMBOL_LENGTH + 1)), ("q", "п" * (MAX_SEARCH_LENGTH + 1))],
)
def test_oversized_text_filters_are_refused(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        query(**{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "любой"), ("direction", "вверх"), ("result", "почти")],
)
def test_dictionary_filters_accept_only_their_words(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        query(**{field: value})


# --- сортировка и курсор ------------------------------------------------------


@pytest.mark.parametrize("raw", ["account_id:desc", "close_time", "close_time:вниз"])
def test_unknown_sort_is_refused(raw: str) -> None:
    with pytest.raises(ValidationError):
        query(sort=raw)


def test_cursor_is_decoded_at_the_boundary() -> None:
    """Разбор курсора здесь — единственная причина, по которой он даёт 400, а не 500."""
    sort = parse_sort("net_pnl:asc")
    position_id = uuid4()
    token = encode_cursor(sort, Decimal("10.50"), position_id)

    parsed = query(sort="net_pnl:asc", cursor=token)

    assert parsed.cursor_key is not None
    assert parsed.cursor_key.value == Decimal("10.50")
    assert parsed.cursor_key.position_id == position_id


def test_broken_cursor_is_refused() -> None:
    with pytest.raises(ValidationError) as raised:
        query(cursor="не-курсор")

    assert raised.value.errors()[0]["loc"] == ("cursor",)


def test_cursor_from_another_sort_is_refused() -> None:
    """Курсор помнит порядок; под другим он указывал бы на другое место списка."""
    token = encode_cursor(parse_sort("close_time:desc"), MOMENT, uuid4())

    with pytest.raises(ValidationError):
        query(sort="net_pnl:asc", cursor=token)


def test_a_broken_sort_does_not_hide_behind_the_cursor() -> None:
    """Сортировка не разобралась — про курсор сказать нечего, и второй ошибки не будет."""
    token = encode_cursor(parse_sort("close_time:desc"), MOMENT, uuid4())

    with pytest.raises(ValidationError) as raised:
        query(sort="мусор", cursor=token)

    assert [error["loc"] for error in raised.value.errors()] == [("sort",)]


# --- вычисляемые поля ответа --------------------------------------------------


@pytest.mark.parametrize(
    ("net_pnl", "expected"),
    [
        (Decimal("0.01"), "win"),
        (Decimal("1000"), "win"),
        (Decimal("-0.01"), "loss"),
        (Decimal("0.00"), "be"),
        (Decimal("0"), "be"),
    ],
)
def test_result_follows_the_spec_thresholds(net_pnl: Decimal, expected: str) -> None:
    """SPEC.md 5.4 дословно: `> 0` win, `< 0` loss, `= 0` breakeven. Полосы вокруг нуля нет."""
    assert position_result(_position(net_pnl=net_pnl)) == expected


def test_open_position_has_no_result() -> None:
    """У незакрытой сделки итога ещё нет, а комиссия входа уже сделала `net_pnl` отрицательным."""
    assert position_result(_position(status="open", net_pnl=Decimal("-0.35"))) is None


def test_notes_preview_collapses_whitespace() -> None:
    assert notes_preview("  первая\n\tвторая   третья  ") == "первая вторая третья"


def test_notes_preview_is_cut_to_one_line_of_a_table() -> None:
    """Без предела страница из 50 строк тащит в таблицу все заметки целиком."""
    preview = notes_preview("я" * (NOTES_PREVIEW_LENGTH * 3))

    assert preview is not None
    assert len(preview) == NOTES_PREVIEW_LENGTH
    assert preview.endswith("…")


def test_notes_preview_keeps_a_short_note_intact() -> None:
    assert notes_preview("коротко") == "коротко"


@pytest.mark.parametrize("notes", [None, "", "   \n  "])
def test_blank_notes_have_no_preview(notes: str | None) -> None:
    assert notes_preview(notes) is None


def test_uuid_list_type_is_uuid_not_string() -> None:
    """`account_id_list` идёт прямо в `where`, поэтому типы там уже доменные."""
    parsed = query(account_ids=str(uuid4()))

    assert all(isinstance(item, UUID) for item in parsed.account_id_list)
