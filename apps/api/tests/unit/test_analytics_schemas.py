"""Границы аналитики: что обязано упасть до запроса к базе, и в какой форме уходит ответ.

Форма ответа проверяется здесь, а не в интеграционном тесте, по одной причине: типы фронта
генерируются из OpenAPI, и «число вместо строки» или «0 вместо null» доедут до экрана
молча. Что фильтры действительно фильтруют — в `tests/integration/test_analytics.py`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domains.analytics import metrics, service
from app.domains.analytics.schemas import (
    CalendarDay,
    CalendarQuery,
    CalendarResponse,
    SummaryQuery,
    SummaryResponse,
)

MOMENT = datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC)


def summary_query(**values: Any) -> SummaryQuery:
    return SummaryQuery.model_validate(values)


def calendar_query(**values: Any) -> CalendarQuery:
    return CalendarQuery.model_validate({"month": "2026-09", **values})


def full_summary(**overrides: Any) -> metrics.Summary:
    values: dict[str, Any] = {
        "trades": 8,
        "wins": 4,
        "losses": 3,
        "breakeven": 1,
        "open_positions": 2,
        "winrate": Decimal("0.5000"),
        "net_pnl": Decimal("117.00"),
        "gross_pnl": Decimal("144.50"),
        "commission": Decimal("-22.00"),
        "swap": Decimal("-4.50"),
        "fee": Decimal("-1.00"),
        "profit_factor": Decimal("2.17"),
        "avg_win": Decimal("54.25"),
        "avg_loss": Decimal("-33.33"),
        "expectancy": Decimal("14.63"),
        "best_trade": Decimal("116.00"),
        "worst_trade": Decimal("-52.00"),
    }
    values.update(overrides)
    return metrics.Summary(**values)


@pytest.mark.parametrize("month", ["2026-09", "2000-01", "2100-12"])
def test_month_is_accepted(month: str) -> None:
    assert calendar_query(month=month).month == month


@pytest.mark.parametrize(
    "month",
    ["2026-9", "2026-13", "2026-00", "сентябрь", "2026", "2026-09-01", "1999-12", "2101-01", ""],
)
def test_month_is_rejected(month: str) -> None:
    """Мусор в параметре — 400 на границе, а не диапазон дней, который база построит."""
    with pytest.raises(ValidationError):
        calendar_query(month=month)


def test_month_splits_into_year_and_month() -> None:
    assert calendar_query(month="2026-09").year_month == (2026, 9)


def test_calendar_requires_month() -> None:
    """Календарь без месяца — не «текущий месяц»: чей он, сервер не знает."""
    with pytest.raises(ValidationError):
        CalendarQuery.model_validate({})


def test_unknown_filter_is_rejected() -> None:
    """`extra="forbid"` из общей базы фильтров: опечатка не должна давать полную выборку."""
    with pytest.raises(ValidationError):
        calendar_query(symbols="EURUSD")
    with pytest.raises(ValidationError):
        summary_query(status="closed")


def test_naive_period_boundary_is_rejected() -> None:
    """Время без зоны — незаданный вопрос, а не UTC по умолчанию."""
    with pytest.raises(ValidationError):
        summary_query(**{"from": "2026-09-01T00:00:00"})


def test_reversed_period_is_rejected() -> None:
    with pytest.raises(ValidationError):
        summary_query(**{"from": "2026-09-02T00:00:00Z", "to": "2026-09-01T00:00:00Z"})


def test_account_ids_must_be_uuids() -> None:
    with pytest.raises(ValidationError):
        summary_query(account_ids="не-uuid")


def test_empty_account_ids_mean_all_accounts() -> None:
    assert summary_query().account_id_list == []
    assert calendar_query().account_id_list == []


def test_summary_money_and_ratios_leave_as_strings() -> None:
    """В JSON нет десятичного типа: число здесь означало бы double на фронте."""
    payload = SummaryResponse.from_summary(full_summary()).model_dump(mode="json")

    assert payload["net_pnl"] == "117.00"
    assert payload["avg_loss"] == "-33.33"
    assert payload["expectancy"] == "14.63"
    assert payload["winrate"] == "0.5000"
    assert payload["profit_factor"] == "2.17"
    # Счётчики остаются числами: они целые и в double не портятся.
    assert payload["trades"] == 8
    assert payload["open_positions"] == 2


def test_summary_keeps_nulls_as_nulls() -> None:
    """`null` значит «нечего считать». Ноль на его месте читался бы как результат."""
    payload = SummaryResponse.from_summary(
        full_summary(
            trades=0,
            wins=0,
            losses=0,
            breakeven=0,
            winrate=None,
            profit_factor=None,
            avg_win=None,
            avg_loss=None,
            expectancy=None,
            best_trade=None,
            worst_trade=None,
            net_pnl=Decimal("0.00"),
        )
    ).model_dump(mode="json")

    assert payload["winrate"] is None
    assert payload["profit_factor"] is None
    assert payload["avg_win"] is None
    assert payload["expectancy"] is None
    # А сумма пустого множества — честный ноль, и он приходит нулём.
    assert payload["net_pnl"] == "0.00"


def test_calendar_day_carries_its_boundaries_in_utc() -> None:
    """Границы дня уходят готовыми: их подставляют в `?from=&to=` журнала как есть."""
    account_id = uuid4()
    day = service.CalendarDay(
        day=date(2026, 9, 2),
        starts_at=datetime(2026, 9, 1, 19, 0, tzinfo=UTC),
        ends_at=datetime(2026, 9, 2, 19, 0, tzinfo=UTC),
        trades=2,
        wins=1,
        losses=1,
        breakeven=0,
        net_pnl=Decimal("10.00"),
        by_account=[service.AccountDay(account_id=account_id, trades=2, net_pnl=Decimal("10.00"))],
    )

    payload = CalendarResponse(
        month="2026-09",
        timezone="Asia/Yekaterinburg",
        day_boundary_hour=0,
        days=[CalendarDay.from_day(day)],
    ).model_dump(mode="json")

    assert payload["days"][0]["day"] == "2026-09-02"
    assert payload["days"][0]["starts_at"] == "2026-09-01T19:00:00Z"
    assert payload["days"][0]["ends_at"] == "2026-09-02T19:00:00Z"
    assert payload["days"][0]["net_pnl"] == "10.00"
    assert payload["days"][0]["by_account"] == [
        {"account_id": str(account_id), "net_pnl": "10.00", "trades": 2}
    ]
    # Правило, по которому нарезаны дни, возвращается вместе с ними.
    assert payload["timezone"] == "Asia/Yekaterinburg"
    assert payload["day_boundary_hour"] == 0
