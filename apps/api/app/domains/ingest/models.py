"""Сделки, позиции, символы и запуски синка (SPEC.md 3.3).

`deals` — append-only факты брокера: в рамках синка они не обновляются и не удаляются.
`positions` пересобираются из `deals` по `unique (account_id, position_id)`, поэтому
`positions.id` переживает пересборку, а вместе с ним — весь пользовательский слой.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7

# Деньги и объёмы: SPEC.md 2.2. Ни одного float в денежных расчётах.
MONEY = Numeric(18, 2)
QUANTITY = Numeric(18, 8)


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = (
        # На этом ограничении стоит идемпотентность POST /ingest/deals (S1-04).
        UniqueConstraint("account_id", "deal_ticket", name="uq_deals_account_id_deal_ticket"),
        Index("ix_deals_account_id_position_id", "account_id", "position_id"),
        Index("ix_deals_account_id_time_utc", "account_id", "time_utc"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    account_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("trading_accounts.id"))
    deal_ticket: Mapped[int] = mapped_column(BigInteger)
    order_ticket: Mapped[int | None] = mapped_column(BigInteger)
    position_id: Mapped[int] = mapped_column(BigInteger)
    symbol_raw: Mapped[str] = mapped_column(Text)
    # 'buy' | 'sell' | 'balance' | 'credit' | 'other' — словарь нормализатора (SPEC.md 6),
    # без check: список пополняется быстрее, чем идут миграции.
    deal_type: Mapped[str] = mapped_column(Text)
    entry: Mapped[str] = mapped_column(Text)  # 'in' | 'out' | 'inout' | 'out_by'
    reason: Mapped[str | None] = mapped_column(Text)
    volume: Mapped[Decimal] = mapped_column(QUANTITY)
    price: Mapped[Decimal] = mapped_column(QUANTITY)
    profit: Mapped[Decimal] = mapped_column(MONEY)
    commission: Mapped[Decimal] = mapped_column(MONEY, server_default=text("0"))
    swap: Mapped[Decimal] = mapped_column(MONEY, server_default=text("0"))
    fee: Mapped[Decimal] = mapped_column(MONEY, server_default=text("0"))
    time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Время сервера брокера как пришло от терминала; хранится в timestamptz (SPEC.md 3.3).
    time_server: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
    magic: Mapped[int | None] = mapped_column(BigInteger)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(Text)  # 'collector' | 'ea' | 'csv' | 'manual'
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint("direction in ('long', 'short')", name="direction"),
        CheckConstraint("status in ('open', 'closed')", name="status"),
        # Ключ UPSERT'а пересборки: сохраняет positions.id, а значит и пользовательский слой.
        UniqueConstraint("account_id", "position_id", name="uq_positions_account_id_position_id"),
        Index("ix_positions_account_id_close_time", "account_id", "close_time"),
        Index("ix_positions_account_id_symbol_norm", "account_id", "symbol_norm"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    account_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("trading_accounts.id"))
    # Из MT5; для ручных сделок генерируется отрицательный (SPEC.md 3.3).
    position_id: Mapped[int] = mapped_column(BigInteger)
    symbol_raw: Mapped[str] = mapped_column(Text)
    symbol_norm: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    close_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    volume_opened: Mapped[Decimal] = mapped_column(QUANTITY)
    volume_closed: Mapped[Decimal] = mapped_column(QUANTITY)
    avg_entry_price: Mapped[Decimal] = mapped_column(QUANTITY)
    avg_exit_price: Mapped[Decimal | None] = mapped_column(QUANTITY)
    gross_pnl: Mapped[Decimal] = mapped_column(MONEY, server_default=text("0"))
    commission: Mapped[Decimal] = mapped_column(MONEY, server_default=text("0"))
    swap: Mapped[Decimal] = mapped_column(MONEY, server_default=text("0"))
    fee: Mapped[Decimal] = mapped_column(MONEY, server_default=text("0"))
    # gross + commission + swap + fee, все со знаком как у брокера.
    net_pnl: Mapped[Decimal] = mapped_column(MONEY, server_default=text("0"))
    deals_count: Mapped[int] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    close_reason: Mapped[str | None] = mapped_column(Text)
    is_manual: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    rebuilt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Symbol(Base):
    __tablename__ = "symbols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw: Mapped[str] = mapped_column(Text, unique=True)  # 'EURUSD.m'
    norm: Mapped[str] = mapped_column(Text)  # 'EURUSD'
    # 'fx' | 'metal' | 'index' | 'crypto' | 'energy' | 'stock' | 'other'
    asset_class: Mapped[str | None] = mapped_column(Text)
    digits: Mapped[int | None] = mapped_column(SmallInteger)
    contract_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    tick_size: Mapped[Decimal | None] = mapped_column(QUANTITY)
    source: Mapped[str] = mapped_column(Text, server_default=text("'auto'"))


class SyncRun(Base):
    __tablename__ = "sync_runs"
    # Таблица читается только как «прогоны этого счёта».
    __table_args__ = (Index("ix_sync_runs_account_id", "account_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # SPEC.md 3.4 не пишет not null, но запуск синка без счёта не существует.
    account_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("trading_accounts.id"))
    source: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deals_received: Mapped[int | None] = mapped_column(Integer, server_default=text("0"))
    deals_new: Mapped[int | None] = mapped_column(Integer, server_default=text("0"))
    positions_rebuilt: Mapped[int | None] = mapped_column(Integer, server_default=text("0"))
    server_utc_offset_minutes: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
