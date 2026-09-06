"""Суточная агрегация — `daily_stats` (SPEC.md 3.4).

**Это кэш, а не источник.** Календарь и сводка считают по `positions` каждый раз, поэтому
устаревшего числа человек не видит в принципе; таблица заполняется задачей
`refresh_daily_stats` (SPEC.md 10) и в v1 никем не читается. Разбор решения и его цена —
`docs/metrics.md` §6.

Три колонки сверх эскиза SPEC.md 3.4 — `timezone`, `day_boundary_hour`, `computed_at` — и
без них таблица была бы ловушкой. День считается по настройкам пользователя, а не только
по сделкам: смена таймзоны или часа границы в настройках (`S0-08`) делает неверными **все**
строки разом, и ни одна задача из SPEC.md 10 на это не подписана. Строка, которая помнит
правило своего расчёта, позволяет читателю это заметить; строка без него — нет.

`on delete cascade` на счёт — пятый каскад в схеме и единственный на производных данных.
Остальные FK намеренно `NO ACTION`, чтобы удаление счёта с фактами падало громко
(`docs/ARCHITECTURE.md`), но здесь фактов нет: строка пересчитывается из `positions` в
любой момент, и переживать удаление счёта ей незачем.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

MONEY = Numeric(18, 2)
QUANTITY = Numeric(18, 8)


class DailyStat(Base):
    __tablename__ = "daily_stats"

    account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("trading_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    # Торговый день пользователя, а не дата UTC (`docs/metrics.md` §2).
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    trades: Mapped[int] = mapped_column(Integer)
    wins: Mapped[int] = mapped_column(Integer)
    losses: Mapped[int] = mapped_column(Integer)
    breakeven: Mapped[int] = mapped_column(Integer)
    gross_pnl: Mapped[Decimal] = mapped_column(MONEY)
    net_pnl: Mapped[Decimal] = mapped_column(MONEY)
    commission: Mapped[Decimal] = mapped_column(MONEY)
    swap: Mapped[Decimal] = mapped_column(MONEY)
    # Есть в `net_pnl`, но нет в эскизе SPEC.md 3.4: без него не сходится
    # `net_pnl = gross_pnl + commission + swap + fee`, и недостача выглядит как ошибка.
    fee: Mapped[Decimal] = mapped_column(MONEY)
    volume: Mapped[Decimal] = mapped_column(QUANTITY)
    # Правило, по которому посчитана строка. Не совпало с настройками пользователя —
    # строку читать нельзя, её надо пересчитать.
    timezone: Mapped[str] = mapped_column(Text)
    day_boundary_hour: Mapped[int] = mapped_column(SmallInteger)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
