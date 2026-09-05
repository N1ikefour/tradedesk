"""Торговые счета и credentials (SPEC.md 3.2)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7

PLATFORMS = ("mt5", "csv", "manual")
ACCOUNT_TYPES = ("hedging", "netting")
ACCOUNT_STATUSES = ("pending", "connected", "needs_attention", "paused", "archived")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in (" + ", ".join(f"'{value}'" for value in values) + ")"


class TradingAccount(Base):
    __tablename__ = "trading_accounts"
    __table_args__ = (
        CheckConstraint(_in_list("platform", PLATFORMS), name="platform"),
        # v1: только USD. Снимается на этапе 7 вместе с конвертацией валют.
        CheckConstraint("currency = 'USD'", name="currency_usd"),
        CheckConstraint(_in_list("account_type", ACCOUNT_TYPES), name="account_type"),
        CheckConstraint(_in_list("status", ACCOUNT_STATUSES), name="status"),
        # Частичный: один и тот же server+login у mt5 — это один счёт, а у csv/manual
        # эти поля произвольны и повторяются.
        Index(
            "uq_trading_accounts_mt5_identity",
            "user_id",
            "platform",
            "server",
            "login",
            unique=True,
            postgresql_where=text("platform = 'mt5'"),
        ),
        # Счета пользователя — фильтр всех пользовательских списков (CLAUDE.md, S0-04).
        Index("ix_trading_accounts_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    label: Mapped[str] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    color: Mapped[str] = mapped_column(Text)
    platform: Mapped[str] = mapped_column(Text)
    broker: Mapped[str | None] = mapped_column(Text)
    server: Mapped[str | None] = mapped_column(Text)
    login: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(CHAR(3), server_default=text("'USD'"))
    account_type: Mapped[str | None] = mapped_column(Text)
    server_utc_offset_minutes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    status_message: Mapped[str | None] = mapped_column(Text)
    # Просьба пользователя на внеочередной синк (SPEC.md 5.2). Коллектор читает её через
    # assignments (5.6) и сравнивает с последним синком (8.2); API её только ставит.
    sync_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collector_id: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccountCredential(Base):
    """Пароль читается только `GET /internal/collector/assignments` (SPEC.md 5.6)."""

    __tablename__ = "account_credentials"

    account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("trading_accounts.id", ondelete="CASCADE"), primary_key=True
    )
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    wrapped_data_key: Mapped[bytes] = mapped_column(LargeBinary)
    key_version: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
