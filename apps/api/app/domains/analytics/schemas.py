"""Параметры и ответы аналитики — SPEC.md 5.5 (сводка) и 5.4 (календарь).

Всё дробное уходит строкой (`MoneyOut`, `RatioOut`): в JSON нет десятичного типа, и число
здесь означало бы double на фронте. Разбор масштабов и округления — `docs/metrics.md` §3.2.

`None` в ответе значит «считать нечего», а не «вышло ноль»: сумма пустого множества это
честный ноль, а среднее и доля пустого множества не существуют. Ноль вместо `null` у
`profit_factor` читался бы как провал там, где на самом деле нет ни одной убыточной
сделки, — самый дорогой из возможных обманов этого экрана (`docs/metrics.md` §3.1).

Два поля сверх перечня SPEC.md 5.5 — `breakeven` и `fee`. Без первого на экране не
сходится `trades = wins + losses + breakeven`, без второго — `net_pnl = gross_pnl +
commission + swap + fee`. Оба расхождения человек обнаруживает калькулятором за минуту, и
объяснять их пришлось бы каждому.
"""

from __future__ import annotations

import re
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.core.query import AccountScopedQuery, PeriodQuery
from app.core.schemas import MoneyOut, RatioOut, UtcDatetime
from app.domains.analytics import metrics, service

MONTH_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
MIN_YEAR = 2000
MAX_YEAR = 2100

MONTH_ERROR = "Месяц задаётся как YYYY-MM, например 2026-09"
MONTH_RANGE_ERROR = f"Год должен быть между {MIN_YEAR} и {MAX_YEAR}"


class SummaryQuery(PeriodQuery):
    """Фильтры `GET /analytics/summary`. Своих полей нет — счета и период общие с журналом."""


class CalendarQuery(AccountScopedQuery):
    """Фильтры `GET /journal/calendar` — SPEC.md 5.4."""

    month: str = Field(description="Месяц в зоне пользователя, YYYY-MM")

    @field_validator("month")
    @classmethod
    def _month(cls, value: str) -> str:
        """Разбор на границе: иначе мусор в параметре доходит до `generate_series`.

        Год ограничен не из вредности — им задаётся длина ряда дней в SQL, и `0001-01`
        просил бы у базы диапазон, который она честно попыталась бы построить.
        """
        matched = MONTH_PATTERN.match(value.strip())
        if matched is None:
            raise PydanticCustomError("month", MONTH_ERROR)
        if not MIN_YEAR <= int(matched.group(1)) <= MAX_YEAR:
            raise PydanticCustomError("month", MONTH_RANGE_ERROR)
        return value.strip()

    @property
    def year_month(self) -> tuple[int, int]:
        year, month = self.month.split("-")
        return int(year), int(month)


class SummaryResponse(BaseModel):
    """Сводка периода — SPEC.md 5.5, формулы `docs/metrics.md` §3."""

    model_config = ConfigDict(extra="forbid")

    trades: int = Field(description="Закрытых позиций за период")
    wins: int
    losses: int
    breakeven: int = Field(description="Закрыты в точный ноль")
    open_positions: int = Field(
        description=(
            "Открытых позиций за период. В денежные суммы не входят: у открытой позиции "
            "в net_pnl лежат накопленные издержки, а не плавающий результат"
        )
    )
    winrate: RatioOut | None = Field(description="Доля выигрышных от всех закрытых, 0…1")
    net_pnl: MoneyOut
    gross_pnl: MoneyOut = Field(description="Результат до издержек, как считает брокер")
    commission: MoneyOut
    swap: MoneyOut
    fee: MoneyOut
    profit_factor: RatioOut | None = Field(
        description="Прибыль на единицу убытка. null — убыточных сделок не было вовсе"
    )
    avg_win: MoneyOut | None
    avg_loss: MoneyOut | None = Field(description="Отрицателен: это деньги, а не модуль")
    expectancy: MoneyOut | None = Field(description="Средний результат сделки")
    best_trade: MoneyOut | None
    worst_trade: MoneyOut | None

    @classmethod
    def from_summary(cls, summary: metrics.Summary) -> SummaryResponse:
        return cls(
            trades=summary.trades,
            wins=summary.wins,
            losses=summary.losses,
            breakeven=summary.breakeven,
            open_positions=summary.open_positions,
            winrate=summary.winrate,
            net_pnl=summary.net_pnl,
            gross_pnl=summary.gross_pnl,
            commission=summary.commission,
            swap=summary.swap,
            fee=summary.fee,
            profit_factor=summary.profit_factor,
            avg_win=summary.avg_win,
            avg_loss=summary.avg_loss,
            expectancy=summary.expectancy,
            best_trade=summary.best_trade,
            worst_trade=summary.worst_trade,
        )


class CalendarAccountDay(BaseModel):
    """Вклад счёта в день — SPEC.md 5.4: `by_account: [{account_id, net_pnl, trades}]`."""

    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    net_pnl: MoneyOut
    trades: int

    @classmethod
    def from_account_day(cls, row: service.AccountDay) -> CalendarAccountDay:
        return cls(account_id=row.account_id, net_pnl=row.net_pnl, trades=row.trades)


class CalendarDay(BaseModel):
    """День календаря. Считаются только закрытые позиции — `docs/metrics.md` §5."""

    model_config = ConfigDict(extra="forbid")

    day: date
    starts_at: UtcDatetime = Field(
        description="Начало торгового дня в UTC — это значение и надо слать в ?from="
    )
    ends_at: UtcDatetime = Field(description="Конец торгового дня в UTC, не включая границу")
    trades: int
    wins: int
    losses: int
    breakeven: int
    net_pnl: MoneyOut
    by_account: list[CalendarAccountDay]

    @classmethod
    def from_day(cls, row: service.CalendarDay) -> CalendarDay:
        return cls(
            day=row.day,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            trades=row.trades,
            wins=row.wins,
            losses=row.losses,
            breakeven=row.breakeven,
            net_pnl=row.net_pnl,
            by_account=[CalendarAccountDay.from_account_day(item) for item in row.by_account],
        )


class CalendarResponse(BaseModel):
    """Месяц календаря.

    Зона и час границы возвращаются вместе с днями не для красоты: по ним видно, по какому
    правилу нарезаны дни. Пересчитывать день на клиенте не нужно и не следует — у каждого
    дня уже есть готовые границы (`docs/metrics.md` §2.2).
    """

    model_config = ConfigDict(extra="forbid")

    month: str
    timezone: str
    day_boundary_hour: int
    days: list[CalendarDay]
