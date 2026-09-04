"""Таблица `dev_outbox` — письма, «отправленные» ConsoleEmailProvider (SPEC.md 4).

В SPEC.md 3 таблицы нет: раздел 4 и DoD S0-04 её требуют, а модель данных не описывает.
Схема согласована в `docs/tickets/S0-04.md`. Тело письма содержит одноразовый код, поэтому
таблица наполняется только console-провайдером, а читается только при APP_ENV=local.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import uuid7


class DevOutboxEntry(Base):
    __tablename__ = "dev_outbox"
    # Без DESC: btree сканируется в обе стороны, а колоночный индекс сравним с отражением
    # схемы (тот же приём, что у ix_otp_codes_email_created_at).
    __table_args__ = (Index("ix_dev_outbox_created_at", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    to_email: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
