"""dev_outbox и индексы по user_id (S0-04)

Revision ID: 8f4c1d90ae27
Revises: b07a46275bbc
Create Date: 2026-09-04 12:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "8f4c1d90ae27"
down_revision: str | None = "b07a46275bbc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # dev_outbox: SPEC.md 4 требует таблицу, раздел 3 её не описывает. Схема — из
    # docs/tickets/S0-04.md. Наполняется только ConsoleEmailProvider.
    op.create_table(
        "dev_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("to_email", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dev_outbox")),
    )
    op.create_index("ix_dev_outbox_created_at", "dev_outbox", ["created_at"], unique=False)

    # Отложенный follow-up ревью S0-03: запросы по user_id появляются в S0-04.
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_index("ix_trading_accounts_user_id", "trading_accounts", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trading_accounts_user_id", table_name="trading_accounts")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_index("ix_dev_outbox_created_at", table_name="dev_outbox")
    op.drop_table("dev_outbox")
