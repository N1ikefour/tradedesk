"""Сводка и календарь — SPEC.md 5.5 и 5.4, формулы в `docs/metrics.md`.

Здесь только запросы: что именно считается — в `metrics.py` (чистые формулы) и
`trading_day.py` (правило дня). Разделение не косметическое — формулы обязаны быть
проверяемы без базы и без часов, иначе первое же расхождение чисел придётся ловить
интеграционным тестом на живом Postgres.

Три правила, из которых растёт модуль.

1. **Считаются закрытые позиции.** У открытой позиции в `positions.net_pnl` лежит не
   плавающий результат, а накопленные издержки (`SPEC.md` §7), и складывать их в шапке
   значило бы красить живые сделки в убыток за комиссию входа. Открытые попадают в ответ
   только счётчиком `open_positions` — он и объясняет человеку, почему сумма колонки в
   журнале может не совпасть с шапкой (`docs/metrics.md` §1.1).
2. **Период и скоуп по счетам — общие с журналом.** `event_time` и `resolve_account_ids`
   импортируются из `journal.service`, а не переписываются: две копии этих правил
   разъехались бы молча, и шапка стала бы считать не то множество строк, которое видно
   в списке. Естественный дом `resolve_account_ids` — домен счетов, переезд туда это
   отдельная задача.
3. **День считает база, а не Python.** Границы дня уходят клиенту готовыми
   (`starts_at`/`ends_at`), поэтому переход «клик по дню → журнал за этот день» ничего не
   вычисляет заново.
"""

from __future__ import annotations

import calendar as calendar_module
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, and_, bindparam, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics import metrics
from app.domains.analytics.trading_day import DAYS_CTE
from app.domains.ingest import models as ingest_models
from app.domains.journal.service import STATUS_CLOSED, event_time, resolve_account_ids

ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class AccountDay:
    """Вклад одного счёта в день — SPEC.md 5.4: `by_account`."""

    account_id: UUID
    trades: int
    net_pnl: Decimal


@dataclass(frozen=True, slots=True)
class CalendarDay:
    day: date
    starts_at: datetime
    ends_at: datetime
    trades: int
    wins: int
    losses: int
    breakeven: int
    net_pnl: Decimal
    by_account: list[AccountDay]


def _or_zero(value: Decimal | None) -> Decimal:
    """Сумма пустого множества — ноль, и это единственное место, где так решается.

    SQL на пустой выборке возвращает `NULL`, а не `0`. Ноль здесь честен именно у сумм;
    у средних и долей его быть не должно, и `metrics.py` их не подменяет (§3.1
    `docs/metrics.md`).
    """
    return ZERO if value is None else value


def _period_clauses(
    date_from: datetime | None, date_to: datetime | None
) -> list[ColumnElement[bool]]:
    clauses: list[ColumnElement[bool]] = []
    if date_from is not None:
        clauses.append(event_time() >= date_from)
    if date_to is not None:
        clauses.append(event_time() < date_to)
    return clauses


async def summary(
    session: AsyncSession,
    user_id: UUID,
    account_ids: Sequence[UUID],
    date_from: datetime | None,
    date_to: datetime | None,
) -> metrics.Summary:
    """Сводка периода одним запросом — SPEC.md 5.5.

    Все счётчики и суммы берутся `FILTER (WHERE …)` из одной выборки, а не отдельными
    запросами на выигрышные и убыточные: так множество строк заведомо одно, и `trades`
    не может разойтись с `wins + losses + breakeven`.
    """
    scoped = await resolve_account_ids(session, user_id, account_ids)
    position = ingest_models.Position
    net = position.net_pnl
    closed = position.status == STATUS_CLOSED

    statement = select(
        func.count().filter(closed).label("trades"),
        func.count().filter(and_(closed, net > 0)).label("wins"),
        func.count().filter(and_(closed, net < 0)).label("losses"),
        func.count().filter(and_(closed, net == 0)).label("breakeven"),
        # «Не закрытая» — это «открытая»: других значений у `status` нет, их запрещает
        # check-констрейнт (SPEC.md 3.3). Отдельная константа завела бы второе написание
        # того же множества.
        func.count().filter(position.status != STATUS_CLOSED).label("open_positions"),
        func.sum(position.gross_pnl).filter(closed).label("gross_pnl"),
        func.sum(net).filter(closed).label("net_pnl"),
        func.sum(position.commission).filter(closed).label("commission"),
        func.sum(position.swap).filter(closed).label("swap"),
        func.sum(position.fee).filter(closed).label("fee"),
        func.sum(net).filter(and_(closed, net > 0)).label("gross_profit"),
        func.sum(net).filter(and_(closed, net < 0)).label("gross_loss"),
        func.max(net).filter(closed).label("best_trade"),
        func.min(net).filter(closed).label("worst_trade"),
    ).where(position.account_id.in_(list(scoped)), *_period_clauses(date_from, date_to))

    row = (await session.execute(statement)).one()
    return metrics.summarize(
        metrics.Totals(
            trades=row.trades,
            wins=row.wins,
            losses=row.losses,
            breakeven=row.breakeven,
            open_positions=row.open_positions,
            gross_pnl=_or_zero(row.gross_pnl),
            net_pnl=_or_zero(row.net_pnl),
            commission=_or_zero(row.commission),
            swap=_or_zero(row.swap),
            fee=_or_zero(row.fee),
            gross_profit=_or_zero(row.gross_profit),
            gross_loss=_or_zero(row.gross_loss),
            best_trade=row.best_trade,
            worst_trade=row.worst_trade,
        )
    )


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Первый и последний **торговые дни** месяца. Это даты, а не моменты.

    Моменты из них делает SQL (`trading_day.py`): месяц в зоне пользователя начинается
    тогда, когда у него начинается день `YYYY-MM-01`, а не в полночь UTC.
    """
    last = calendar_module.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


_CALENDAR_SQL = text(
    f"""
with {DAYS_CTE},
positions_of_days as (
    select days.day, days.starts_at, days.ends_at, p.account_id, p.net_pnl
    from days
    join positions p
      on p.close_time >= days.starts_at
     and p.close_time < days.ends_at
    where p.account_id in :account_ids
      and p.status = :closed_status
)
select
    day,
    starts_at,
    ends_at,
    account_id,
    grouping(account_id) as is_day_total,
    count(*) as trades,
    count(*) filter (where net_pnl > 0) as wins,
    count(*) filter (where net_pnl < 0) as losses,
    count(*) filter (where net_pnl = 0) as breakeven,
    sum(net_pnl) as net_pnl
from positions_of_days
group by grouping sets ((day, starts_at, ends_at), (day, starts_at, ends_at, account_id))
order by day, grouping(account_id) desc, account_id
"""
).bindparams(bindparam("account_ids", expanding=True))


async def calendar(
    session: AsyncSession,
    user_id: UUID,
    account_ids: Sequence[UUID],
    year: int,
    month: int,
    timezone: str,
    day_boundary_hour: int,
) -> list[CalendarDay]:
    """Дни месяца с итогами и разбивкой по счетам — SPEC.md 5.4.

    Итог дня и разбивка считаются одним `GROUPING SETS`, а не двумя запросами: сумма
    разбивки обязана совпадать с итогом дня, и проще сделать это невозможным нарушить,
    чем ловить расхождение тестом.

    Дни без закрытых позиций в ответ не попадают: сетку месяца рисует фронт, и отдавать
    два-три десятка нулевых строк в каждом ответе незачем.
    """
    scoped = await resolve_account_ids(session, user_id, account_ids)
    if not scoped:
        # У пользователя нет ни одного счёта. Запрос с пустым списком отправлять нельзя:
        # `in :account_ids` с пустым набором SQLAlchemy разворачивает в `in (NULL)` без
        # типа, и Postgres отвечает ошибкой оператора, а не пустой выборкой. Считать
        # тут всё равно нечего.
        return []
    first_day, last_day = month_bounds(year, month)
    rows = (
        await session.execute(
            _CALENDAR_SQL,
            {
                "timezone": timezone,
                "day_boundary_hour": day_boundary_hour,
                "first_day": first_day,
                "last_day": last_day,
                "account_ids": list(scoped),
                "closed_status": STATUS_CLOSED,
            },
        )
    ).all()
    return _fold_calendar_rows(rows)


def _fold_calendar_rows(rows: Sequence[Any]) -> list[CalendarDay]:
    """Строки `GROUPING SETS` в дни: `is_day_total = 1` — итог, остальные — счета.

    Порядок гарантирован `ORDER BY` запроса: итог дня приходит раньше своих счетов.
    """
    days: list[CalendarDay] = []
    for row in rows:
        if row.is_day_total:
            days.append(
                CalendarDay(
                    day=row.day,
                    starts_at=row.starts_at,
                    ends_at=row.ends_at,
                    trades=row.trades,
                    wins=row.wins,
                    losses=row.losses,
                    breakeven=row.breakeven,
                    net_pnl=_or_zero(row.net_pnl),
                    by_account=[],
                )
            )
            continue
        days[-1].by_account.append(
            AccountDay(account_id=row.account_id, trades=row.trades, net_pnl=_or_zero(row.net_pnl))
        )
    return days
