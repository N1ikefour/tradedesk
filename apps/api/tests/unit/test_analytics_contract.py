"""Контракт аналитики по объявленной схеме — S2-05.

Фронт (`S2-06` шапка, `S2-09` календарь, `S2-10` дашборд) генерирует типы из OpenAPI, а не
читает этот код, поэтому проверяется обещание, а не реализация. Молча ломаются здесь три
вещи.

* **Дробное число вместо строки.** `number` в схеме означает double на фронте: копейки
  теряются на больших суммах, а `winrate` вида `0.5000` превращается в `0.5` и перестаёт
  отличаться от `0.4999`.
* **Поле, у которого пропал `null`.** `winrate`, `profit_factor` и средние обязаны уметь
  быть пустыми: `null` это «нечего считать», и клиент, у которого тип не допускает
  пустоты, нарисует ноль (`docs/metrics.md` §3.1).
* **Изменившийся состав ответа.** Множества полей заморожены: и забытое поле, и лишнее —
  одинаково дефект, и правка множества видна в ревью.

Значения проверяет `tests/integration/test_analytics.py`, формулы — `test_metrics.py`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI

API = "/api/v1"

EXPECTED_ROUTES = {
    (f"{API}/analytics/summary", "get"),
    (f"{API}/journal/calendar", "get"),
}

# SPEC.md 5.5 плюс `breakeven` и `fee`: без них на экране не сходится
# `trades = wins + losses + breakeven` и `net_pnl = gross_pnl + commission + swap + fee`.
SUMMARY_FIELDS = frozenset(
    {
        "trades",
        "wins",
        "losses",
        "breakeven",
        "open_positions",
        "winrate",
        "net_pnl",
        "gross_pnl",
        "commission",
        "swap",
        "fee",
        "profit_factor",
        "avg_win",
        "avg_loss",
        "expectancy",
        "best_trade",
        "worst_trade",
    }
)

# SPEC.md 5.4 плюс `breakeven` (то же тождество) и границы дня: по ним клиент открывает
# журнал за день, ничего не вычисляя (`docs/metrics.md` §2.2).
CALENDAR_DAY_FIELDS = frozenset(
    {
        "day",
        "starts_at",
        "ends_at",
        "trades",
        "wins",
        "losses",
        "breakeven",
        "net_pnl",
        "by_account",
    }
)

CALENDAR_ACCOUNT_FIELDS = frozenset({"account_id", "net_pnl", "trades"})
CALENDAR_FIELDS = frozenset({"month", "timezone", "day_boundary_hour", "days"})

# Всё дробное в этом домене — строка. Целые счётчики остаются числами.
DECIMAL_FIELDS = frozenset(
    {
        "winrate",
        "profit_factor",
        "net_pnl",
        "gross_pnl",
        "commission",
        "swap",
        "fee",
        "avg_win",
        "avg_loss",
        "expectancy",
        "best_trade",
        "worst_trade",
    }
)

NULLABLE_FIELDS = frozenset(
    {"winrate", "profit_factor", "avg_win", "avg_loss", "expectancy", "best_trade", "worst_trade"}
)


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


def test_analytics_declares_exactly_its_two_routes(document: dict[str, Any]) -> None:
    """Сводка и календарь. Остальная аналитика — этап 3, её в схеме быть не должно."""
    declared = {
        (path, method)
        for path, item in document["paths"].items()
        if path.startswith(f"{API}/analytics") or path == f"{API}/journal/calendar"
        for method, operation in item.items()
        if isinstance(operation, dict) and "responses" in operation
    }

    assert declared == EXPECTED_ROUTES


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("SummaryResponse", SUMMARY_FIELDS),
        ("CalendarDay", CALENDAR_DAY_FIELDS),
        ("CalendarAccountDay", CALENDAR_ACCOUNT_FIELDS),
        ("CalendarResponse", CALENDAR_FIELDS),
    ],
)
def test_models_declare_exactly_the_allowed_fields(
    document: dict[str, Any], model: str, expected: frozenset[str]
) -> None:
    """Равенство, а не подмножество: и забытое поле, и лишнее — одинаково дефект."""
    schema = _component(document, model)

    assert set(schema["properties"]) == set(expected)
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize("model", ["SummaryResponse", "CalendarDay", "CalendarAccountDay"])
def test_decimal_fields_are_strings(document: dict[str, Any], model: str) -> None:
    """Число в схеме — double на фронте, а деньги и доли double не переживают."""
    properties = _component(document, model)["properties"]

    for name, node in properties.items():
        if name not in DECIMAL_FIELDS:
            continue
        types = {variant.get("type") for variant in _variants(node)}
        assert "string" in types, name
        assert "number" not in types, name


def test_fields_that_may_be_empty_declare_null(document: dict[str, Any]) -> None:
    """`null` — «нечего считать». Тип без пустоты заставит клиента нарисовать ноль."""
    properties = _component(document, "SummaryResponse")["properties"]

    for name in NULLABLE_FIELDS:
        types = {variant.get("type") for variant in _variants(properties[name])}
        assert "null" in types, name


def test_counters_stay_numbers(document: dict[str, Any]) -> None:
    """Целые счётчики строкой не отдаются: в double они не портятся, а разбор мешает."""
    properties = _component(document, "SummaryResponse")["properties"]

    for name in ("trades", "wins", "losses", "breakeven", "open_positions"):
        assert properties[name]["type"] == "integer", name


def test_both_routes_declare_the_foreign_account_error(document: dict[str, Any]) -> None:
    """Чужой `account_id` — `404 account_not_found`, как в списке журнала, а не пустая сводка."""
    for path, _method in EXPECTED_ROUTES:
        responses = document["paths"][path]["get"]["responses"]
        assert "404" in responses, path
        description = str(responses["404"])
        assert "account_not_found" in description, path
