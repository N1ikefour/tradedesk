"""sync_requested_at у trading_accounts (S1-06)

Revision ID: c3a91f4d27be
Revises: 8f4c1d90ae27
Create Date: 2026-09-05 19:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "c3a91f4d27be"
down_revision: str | None = "8f4c1d90ae27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Колонку требуют SPEC.md 5.2 (`POST /accounts/{id}/sync-now`), 5.6 (assignments отдают
    # её коллектору) и 8.2 (коллектор сравнивает её с последним синком), а DDL раздела 3.2
    # её не описывал — дефект спеки, подтверждён оркестратором при постановке S1-06.
    #
    # Nullable и без default по SPEC.md 11.4: `null` здесь значит «внеочередной синк никто
    # не просил», и это же верно для всех существующих строк. Default `now()` объявил бы
    # обратное — что синк запрошен для каждого уже заведённого счёта.
    op.add_column(
        "trading_accounts",
        sa.Column("sync_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trading_accounts", "sync_requested_at")
