"""daily_stats — суточная агрегация (S2-05)

Revision ID: e5d7c9a1b348
Revises: c3a91f4d27be
Create Date: 2026-09-06 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5d7c9a1b348"
down_revision: str | None = "c3a91f4d27be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Таблица из SPEC.md 3.4, отложенная до появления потребителя (SPEC.md 12, S2-05).
    # Это **кэш**: календарь и сводка считают по `positions`, а сюда пишет задача
    # `refresh_daily_stats`. Разбор решения — `docs/metrics.md` §6.
    #
    # Три колонки сверх эскиза 3.4. `fee` — потому что он входит в `net_pnl`, и без него
    # строка не сходится сама с собой. `timezone` и `day_boundary_hour` — потому что день
    # нарезан по настройкам пользователя: сменил зону, и все строки посчитаны по другому
    # правилу. Без них протухание неотличимо от свежести.
    #
    # `on delete cascade` — единственный каскад в схеме на производных данных. Остальные
    # FK на `trading_accounts` намеренно `NO ACTION`, чтобы удаление счёта с фактами
    # падало громко; здесь фактов нет, строка пересчитывается из `positions` в любой
    # момент, и удерживать ею удаление счёта не за что.
    op.create_table(
        "daily_stats",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("trades", sa.Integer(), nullable=False),
        sa.Column("wins", sa.Integer(), nullable=False),
        sa.Column("losses", sa.Integer(), nullable=False),
        sa.Column("breakeven", sa.Integer(), nullable=False),
        sa.Column("gross_pnl", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("net_pnl", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("commission", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("swap", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("fee", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("volume", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("day_boundary_hour", sa.SmallInteger(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["trading_accounts.id"],
            name=op.f("fk_daily_stats_account_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", "day", name=op.f("pk_daily_stats")),
    )


def downgrade() -> None:
    op.drop_table("daily_stats")
