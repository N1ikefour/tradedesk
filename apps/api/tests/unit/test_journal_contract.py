"""Контракт журнала по объявленной схеме — S2-01.

Фронт (`S2-06`) генерирует типы из OpenAPI (`make types`), поэтому проверяется не код, а
то, что приложение обещает. Три вещи ломаются в этом домене молча:

* **`deals.raw` и `time_server`.** В `raw` лежит полный ответ терминала. Одна строка в
  модели ответа — и он уезжает клиенту целиком; в диффе это выглядит как «добавил поле».
* **Деньги числом.** В JSON нет десятичного типа: `number` означает double на фронте,
  а `numeric(18,2)` теряет и масштаб, и точность на больших суммах.
* **Лишний маршрут.** `S2-02`…`S2-04` живут отдельными задачами; появившийся здесь
  черновик `PUT entry` попал бы в схему и в типы фронта раньше своей задачи.

Значения (а не имена и типы) проверяет `tests/integration/test_journal.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI

from app.core.openapi import JSON_MEDIA_TYPE

API = "/api/v1"
JOURNAL = f"{API}/journal"

# Ровно два `GET` из SPEC.md 5.4. Остальное — S2-02…S2-04.
EXPECTED_ROUTES = {
    (f"{JOURNAL}/positions", "get"),
    (f"{JOURNAL}/positions/{{position_id}}", "get"),
}

# Колонки позиции из SPEC.md 3.3 плюс вычисленный `result`. Список заморожен: правка
# этого множества — единственный способ добавить поле в ответ, и она видна в ревью.
POSITION_FIELDS = frozenset(
    {
        "id",
        "position_id",
        "symbol_raw",
        "symbol_norm",
        "direction",
        "status",
        "result",
        "open_time",
        "close_time",
        "volume_opened",
        "volume_closed",
        "avg_entry_price",
        "avg_exit_price",
        "gross_pnl",
        "commission",
        "swap",
        "fee",
        "net_pnl",
        "deals_count",
        "duration_seconds",
        "close_reason",
        "is_manual",
        "rebuilt_at",
    }
)

LIST_ITEM_FIELDS = POSITION_FIELDS | {
    "account",
    "journal_entry",
    "reflection",
    "attachments_count",
}
CARD_FIELDS = LIST_ITEM_FIELDS | {"deals"}

# `raw` и `time_server` здесь нет намеренно — см. шапку модуля.
DEAL_FIELDS = frozenset(
    {
        "deal_ticket",
        "order_ticket",
        "symbol_raw",
        "deal_type",
        "entry",
        "reason",
        "volume",
        "price",
        "profit",
        "commission",
        "swap",
        "fee",
        "time_utc",
        "comment",
        "magic",
        "source",
    }
)

FORBIDDEN_DEAL_FIELDS = ("raw", "time_server", "ingested_at", "id", "account_id")

# Всё, что в базе `numeric`. В JSON уходит строкой (`core.schemas.Money`, `Quantity`).
DECIMAL_FIELDS = {
    "PositionListItem": (
        "volume_opened",
        "volume_closed",
        "avg_entry_price",
        "avg_exit_price",
        "gross_pnl",
        "commission",
        "swap",
        "fee",
        "net_pnl",
    ),
    "PositionCard": ("net_pnl", "gross_pnl", "avg_entry_price"),
    "DealResponse": ("volume", "price", "profit", "commission", "swap", "fee"),
    "JournalEntryBrief": ("risk_amount",),
    "JournalEntryDetail": ("planned_entry", "planned_sl", "planned_tp", "risk_amount"),
}

TIME_FIELDS = {
    "PositionListItem": ("open_time", "close_time", "rebuilt_at"),
    "DealResponse": ("time_utc",),
    "ReflectionBrief": ("filled_at",),
}

# Подстроки, а не точные имена: `investor_password` — такая же утечка, как `password`,
# и переименование поля не должно быть способом обойти проверку.
SECRET_NAME_MARKERS = ("password", "secret", "credential", "ciphertext", "wrapped", "token")

# А эти — наоборот, только целиком: `raw` подстрокой совпал бы с легальным `symbol_raw`.
FORBIDDEN_FIELD_NAMES = frozenset({"raw", "time_server"})


@pytest.fixture
def app(unreachable_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]) -> FastAPI:
    """Зависимости смотрят в закрытый порт: до Postgres эти проверки не доходят."""
    return make_app()


@pytest.fixture
def document(app: FastAPI) -> dict[str, Any]:
    return app.openapi()


def _component(document: dict[str, Any], name: str) -> dict[str, Any]:
    schema = document["components"]["schemas"][name]
    assert isinstance(schema, dict)
    return schema


def _variants(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Сама схема плюс ветки `anyOf`: необязательное поле описано объединением с `null`."""
    return [node, *(item for item in node.get("anyOf", []) if isinstance(item, dict))]


def _declared_types(node: dict[str, Any]) -> set[str]:
    return {variant["type"] for variant in _variants(node) if "type" in variant}


def _resolve(document: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    reference = node.get("$ref")
    if reference is None:
        return node
    target: Any = document
    for part in reference.removeprefix("#/").split("/"):
        target = target[part]
    assert isinstance(target, dict)
    return target


def _property_names(document: dict[str, Any], node: Any, seen: set[str]) -> set[str]:
    """Все имена полей, достижимые из схемы. Циклы обрываются по имени компонента."""
    if isinstance(node, list):
        return set().union(*(_property_names(document, item, seen) for item in node), set())
    if not isinstance(node, dict):
        return set()
    reference = node.get("$ref")
    if reference is not None:
        if reference in seen:
            return set()
        return _property_names(document, _resolve(document, node), seen | {reference})
    found: set[str] = set()
    for key, value in node.items():
        if key == "properties" and isinstance(value, dict):
            found |= set(value)
        found |= _property_names(document, value, seen)
    return found


def _journal_success_schemas(document: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    for path, item in document["paths"].items():
        if not path.startswith(JOURNAL):
            continue
        for method, operation in item.items():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            for status_code, response in operation["responses"].items():
                content = response.get("content", {}).get(JSON_MEDIA_TYPE)
                if status_code.startswith("2") and content is not None:
                    found.append((f"{method.upper()} {path}", content["schema"]))
    return found


# --- границы задачи -----------------------------------------------------------


def test_journal_declares_exactly_two_reads(document: dict[str, Any]) -> None:
    """S2-01 — только список и карточка; правки, вложения и теги приходят своими задачами."""
    declared = {
        (path, method)
        for path, item in document["paths"].items()
        if path.startswith(JOURNAL)
        for method, operation in item.items()
        if isinstance(operation, dict) and "responses" in operation
    }

    assert declared == EXPECTED_ROUTES


# --- состав ответа заморожен ---------------------------------------------------


@pytest.mark.parametrize(
    ("model", "expected"),
    [("PositionListItem", LIST_ITEM_FIELDS), ("PositionCard", CARD_FIELDS)],
)
def test_position_models_declare_exactly_the_allowed_fields(
    document: dict[str, Any], model: str, expected: frozenset[str] | set[str]
) -> None:
    """Равенство, а не подмножество: и забытое поле, и лишнее — одинаково дефект."""
    schema = _component(document, model)

    assert set(schema["properties"]) == set(expected)
    assert schema["additionalProperties"] is False


def test_deal_response_declares_exactly_the_allowed_fields(document: dict[str, Any]) -> None:
    schema = _component(document, "DealResponse")

    assert set(schema["properties"]) == set(DEAL_FIELDS)
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize("name", FORBIDDEN_DEAL_FIELDS)
def test_deal_response_hides_the_terminal_dump_and_internals(
    document: dict[str, Any], name: str
) -> None:
    """`raw` — полный ответ терминала, `time_server` — отладка (SPEC.md 3.3)."""
    assert name not in _component(document, "DealResponse")["properties"]


def test_no_journal_response_leaks_a_secret_field(document: dict[str, Any]) -> None:
    """Ни один успешный ответ домена не упоминает пароль и дамп терминала — ни под каким именем."""
    leaks: list[str] = []
    for where, schema in _journal_success_schemas(document):
        for name in _property_names(document, schema, set()):
            lowered = name.lower()
            if lowered in FORBIDDEN_FIELD_NAMES or any(
                marker in lowered for marker in SECRET_NAME_MARKERS
            ):
                leaks.append(f"{where}: поле {name!r}")

    assert leaks == [], f"утечка в ответе журнала: {leaks}"


# --- типы, которые увидит фронт ------------------------------------------------


@pytest.mark.parametrize(
    ("model", "field"),
    [(model, field) for model, fields in DECIMAL_FIELDS.items() for field in fields],
)
def test_decimals_are_declared_as_strings(document: dict[str, Any], model: str, field: str) -> None:
    """`number` заставил бы фронт складывать деньги в double (CLAUDE.md §2).

    Заодно ловится то, чего pydantic хочет по умолчанию: без `WithJsonSchema` он описывает
    `Decimal` как `anyOf[number, string]`, и `make types` дал бы фронту `number | string`.
    """
    declared = _component(document, model)["properties"][field]

    assert _declared_types(declared) <= {"string", "null"}, declared
    assert "string" in _declared_types(declared), declared


@pytest.mark.parametrize(
    ("model", "field"),
    [(model, field) for model, fields in TIME_FIELDS.items() for field in fields],
)
def test_times_are_declared_as_date_time_strings(
    document: dict[str, Any], model: str, field: str
) -> None:
    declared = _component(document, model)["properties"][field]
    formats = {variant.get("format") for variant in _variants(declared)}

    assert _declared_types(declared) <= {"string", "null"}
    assert "date-time" in formats, declared


def test_page_envelope_matches_spec_5_1(document: dict[str, Any]) -> None:
    """`{"items": [...], "next_cursor": "…"|null}` — конверт списков SPEC.md 5.1."""
    schema = _component(document, "PositionsPage")

    assert set(schema["properties"]) == {"items", "next_cursor"}
    assert set(schema["required"]) == {"items", "next_cursor"}
    assert _declared_types(schema["properties"]["next_cursor"]) == {"string", "null"}


def test_result_is_declared_as_the_spec_dictionary(document: dict[str, Any]) -> None:
    """SPEC.md 5.4: win / loss / be, и `null` у открытой позиции."""
    declared = _component(document, "PositionListItem")["properties"]["result"]
    values = {value for variant in _variants(declared) for value in variant.get("enum", ())}

    assert values == {"win", "loss", "be"}
    assert "null" in _declared_types(declared)


def test_account_brief_is_exactly_what_the_spec_promises(document: dict[str, Any]) -> None:
    """SPEC.md 5.4 обещает в строке журнала `account {id,label,color,is_demo}` — и не больше."""
    schema = _component(document, "AccountBrief")

    assert set(schema["properties"]) == {"id", "label", "color", "is_demo"}


def test_reflection_in_the_list_is_only_its_filled_at(document: dict[str, Any]) -> None:
    """SPEC.md 5.4 обещает в списке `reflection.filled_at`; всё остальное — в карточке."""
    assert set(_component(document, "ReflectionBrief")["properties"]) == {"filled_at"}


def test_sort_and_filters_are_documented_for_the_frontend(document: dict[str, Any]) -> None:
    """Названия фильтров — контракт S2-06; `from`/`to` уходят под своими псевдонимами."""
    parameters = document["paths"][f"{JOURNAL}/positions"]["get"]["parameters"]
    names = {parameter["name"] for parameter in parameters}

    assert names == {
        "account_ids",
        "status",
        "from",
        "to",
        "symbol",
        "direction",
        "result",
        "tags",
        "has_reflection",
        "q",
        "sort",
        "limit",
        "cursor",
    }
