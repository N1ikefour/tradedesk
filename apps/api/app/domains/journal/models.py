"""Пользовательский слой журнала (SPEC.md 3.4).

Эти таблицы никогда не затираются пересборкой позиций: они висят на `positions.id`,
который UPSERT пересборки сохраняет. `on delete cascade` здесь — единственный способ,
которым записи исчезают.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
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
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7

MONEY = Numeric(18, 2)
PRICE = Numeric(18, 8)

_EMPTY_ARRAY = text("'{}'::text[]")


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    position_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("positions.id", ondelete="CASCADE"), primary_key=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=_EMPTY_ARRAY)
    planned_entry: Mapped[Decimal | None] = mapped_column(PRICE)
    planned_sl: Mapped[Decimal | None] = mapped_column(PRICE)
    planned_tp: Mapped[Decimal | None] = mapped_column(PRICE)
    # Если задано — R считается от него (SPEC.md 3.4).
    risk_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Reflection(Base):
    __tablename__ = "reflections"
    __table_args__ = (
        CheckConstraint("setup_grade in ('A', 'B', 'C', 'D')", name="setup_grade"),
        CheckConstraint("execution_grade in ('A', 'B', 'C', 'D')", name="execution_grade"),
        CheckConstraint("confidence between 1 and 5", name="confidence"),
    )

    position_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("positions.id", ondelete="CASCADE"), primary_key=True
    )
    setup_grade: Mapped[str | None] = mapped_column(Text)
    execution_grade: Mapped[str | None] = mapped_column(Text)
    followed_plan: Mapped[bool | None] = mapped_column(Boolean)
    # Значения — из словарей SPEC.md 3.5 (vocab.py появится в S2-01).
    emotion_before: Mapped[str | None] = mapped_column(Text)
    emotion_during: Mapped[str | None] = mapped_column(Text)
    emotion_after: Mapped[str | None] = mapped_column(Text)
    mistakes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=_EMPTY_ARRAY)
    confidence: Mapped[int | None] = mapped_column(SmallInteger)
    free_text: Mapped[str | None] = mapped_column(Text)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Attachment(Base):
    __tablename__ = "attachments"
    # Единственная дочерняя таблица positions, где position_id не PK, а значит не индексирован:
    # без индекса каждый delete из positions проверяет каскад сиквенс-сканом.
    __table_args__ = (Index("ix_attachments_position_id", "position_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # SPEC.md 3.4 не пишет not null, но вложение без позиции осиротеет мимо cascade.
    position_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("positions.id", ondelete="CASCADE"))
    s3_key: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Tag(Base):
    """Словарь тегов пользователя. Сами теги на позиции лежат в `journal_entries.tags`."""

    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_tags_user_id_name"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    # SPEC.md 3.4 не пишет not null, но unique (user_id, name) на NULL не работает.
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(Text)
