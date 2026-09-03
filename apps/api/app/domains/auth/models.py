"""Таблицы пользователей и аутентификации (SPEC.md 3.1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # citext: почта регистронезависима, сравнение делает БД, а не каждый вызывающий.
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, server_default=text("'Europe/Moscow'"))
    day_boundary_hour: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OtpCode(Base):
    __tablename__ = "otp_codes"
    # Порядок в индексе — как в SPEC.md 3.1, но без DESC: btree сканируется в обе стороны,
    # а колоночный индекс сравним с отражением схемы (см. tests/integration/test_core_schema.py).
    __table_args__ = (Index("ix_otp_codes_email_created_at", "email", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # Не FK на users: код запрашивают до того, как пользователь заведён (SPEC.md 4).
    email: Mapped[str] = mapped_column(CITEXT)
    code_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"

    # Значение cookie. Генератор задаёт S0-04: uuid7 раскрывает время создания, и для
    # секрета сессии это плохой выбор — здесь default намеренно не проставлен.
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(Text)
