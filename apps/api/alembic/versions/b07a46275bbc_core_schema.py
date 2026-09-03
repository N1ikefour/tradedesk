"""Ядро схемы: пользователи, счета, сделки, позиции, журнал (SPEC.md 3, кроме daily_stats)

Revision ID: b07a46275bbc
Revises:
Create Date: 2026-09-04 01:11:16.897554
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b07a46275bbc"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # citext нужен до создания users и otp_codes: их email объявлен этим типом.
    # Расширение trusted начиная с PG 13 — суперпользователь не требуется.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "otp_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_otp_codes")),
    )
    op.create_index(
        "ix_otp_codes_email_created_at", "otp_codes", ["email", "created_at"], unique=False
    )
    op.create_table(
        "symbols",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("raw", sa.Text(), nullable=False),
        sa.Column("norm", sa.Text(), nullable=False),
        sa.Column("asset_class", sa.Text(), nullable=True),
        sa.Column("digits", sa.SmallInteger(), nullable=True),
        sa.Column("contract_size", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("tick_size", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("source", sa.Text(), server_default=sa.text("'auto'"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_symbols")),
        sa.UniqueConstraint("raw", name=op.f("uq_symbols_raw")),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("timezone", sa.Text(), server_default=sa.text("'Europe/Moscow'"), nullable=False),
        sa.Column(
            "day_boundary_hour", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_sessions_user_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_tags_user_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("user_id", "name", name="uq_tags_user_id_name"),
    )
    op.create_table(
        "trading_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("color", sa.Text(), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("broker", sa.Text(), nullable=True),
        sa.Column("server", sa.Text(), nullable=True),
        sa.Column("login", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), server_default=sa.text("'USD'"), nullable=False),
        sa.Column("account_type", sa.Text(), nullable=True),
        sa.Column("server_utc_offset_minutes", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collector_id", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "account_type in ('hedging', 'netting')", name=op.f("ck_trading_accounts_account_type")
        ),
        sa.CheckConstraint("currency = 'USD'", name=op.f("ck_trading_accounts_currency_usd")),
        sa.CheckConstraint(
            "platform in ('mt5', 'csv', 'manual')", name=op.f("ck_trading_accounts_platform")
        ),
        sa.CheckConstraint(
            "status in ('pending', 'connected', 'needs_attention', 'paused', 'archived')",
            name=op.f("ck_trading_accounts_status"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_trading_accounts_user_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trading_accounts")),
    )
    op.create_index(
        "uq_trading_accounts_mt5_identity",
        "trading_accounts",
        ["user_id", "platform", "server", "login"],
        unique=True,
        postgresql_where=sa.text("platform = 'mt5'"),
    )
    op.create_table(
        "account_credentials",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("wrapped_data_key", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["trading_accounts.id"],
            name=op.f("fk_account_credentials_account_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("account_id", name=op.f("pk_account_credentials")),
    )
    op.create_table(
        "deals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("deal_ticket", sa.BigInteger(), nullable=False),
        sa.Column("order_ticket", sa.BigInteger(), nullable=True),
        sa.Column("position_id", sa.BigInteger(), nullable=False),
        sa.Column("symbol_raw", sa.Text(), nullable=False),
        sa.Column("deal_type", sa.Text(), nullable=False),
        sa.Column("entry", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("volume", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("profit", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column(
            "commission",
            sa.Numeric(precision=18, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "swap", sa.Numeric(precision=18, scale=2), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "fee", sa.Numeric(precision=18, scale=2), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("time_server", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("magic", sa.BigInteger(), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["trading_accounts.id"], name=op.f("fk_deals_account_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deals")),
        sa.UniqueConstraint("account_id", "deal_ticket", name="uq_deals_account_id_deal_ticket"),
    )
    op.create_index(
        "ix_deals_account_id_position_id", "deals", ["account_id", "position_id"], unique=False
    )
    op.create_index(
        "ix_deals_account_id_time_utc", "deals", ["account_id", "time_utc"], unique=False
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("position_id", sa.BigInteger(), nullable=False),
        sa.Column("symbol_raw", sa.Text(), nullable=False),
        sa.Column("symbol_norm", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("open_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("volume_opened", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("volume_closed", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("avg_entry_price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("avg_exit_price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column(
            "gross_pnl",
            sa.Numeric(precision=18, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "commission",
            sa.Numeric(precision=18, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "swap", sa.Numeric(precision=18, scale=2), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "fee", sa.Numeric(precision=18, scale=2), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "net_pnl",
            sa.Numeric(precision=18, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("deals_count", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("close_reason", sa.Text(), nullable=True),
        sa.Column("is_manual", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("rebuilt_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("direction in ('long', 'short')", name=op.f("ck_positions_direction")),
        sa.CheckConstraint("status in ('open', 'closed')", name=op.f("ck_positions_status")),
        sa.ForeignKeyConstraint(
            ["account_id"], ["trading_accounts.id"], name=op.f("fk_positions_account_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_positions")),
        sa.UniqueConstraint(
            "account_id", "position_id", name="uq_positions_account_id_position_id"
        ),
    )
    op.create_index(
        "ix_positions_account_id_close_time",
        "positions",
        ["account_id", "close_time"],
        unique=False,
    )
    op.create_index(
        "ix_positions_account_id_symbol_norm",
        "positions",
        ["account_id", "symbol_norm"],
        unique=False,
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deals_received", sa.Integer(), server_default=sa.text("0"), nullable=True),
        sa.Column("deals_new", sa.Integer(), server_default=sa.text("0"), nullable=True),
        sa.Column("positions_rebuilt", sa.Integer(), server_default=sa.text("0"), nullable=True),
        sa.Column("server_utc_offset_minutes", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"], ["trading_accounts.id"], name=op.f("fk_sync_runs_account_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_runs")),
    )
    op.create_index("ix_sync_runs_account_id", "sync_runs", ["account_id"], unique=False)
    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("position_id", sa.Uuid(), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["positions.id"],
            name=op.f("fk_attachments_position_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attachments")),
    )
    op.create_index("ix_attachments_position_id", "attachments", ["position_id"], unique=False)
    op.create_table(
        "journal_entries",
        sa.Column("position_id", sa.Uuid(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("planned_entry", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("planned_sl", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("planned_tp", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("risk_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["positions.id"],
            name=op.f("fk_journal_entries_position_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("position_id", name=op.f("pk_journal_entries")),
    )
    op.create_table(
        "reflections",
        sa.Column("position_id", sa.Uuid(), nullable=False),
        sa.Column("setup_grade", sa.Text(), nullable=True),
        sa.Column("execution_grade", sa.Text(), nullable=True),
        sa.Column("followed_plan", sa.Boolean(), nullable=True),
        sa.Column("emotion_before", sa.Text(), nullable=True),
        sa.Column("emotion_during", sa.Text(), nullable=True),
        sa.Column("emotion_after", sa.Text(), nullable=True),
        sa.Column(
            "mistakes",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("confidence", sa.SmallInteger(), nullable=True),
        sa.Column("free_text", sa.Text(), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "execution_grade in ('A', 'B', 'C', 'D')", name=op.f("ck_reflections_execution_grade")
        ),
        sa.CheckConstraint(
            "setup_grade in ('A', 'B', 'C', 'D')", name=op.f("ck_reflections_setup_grade")
        ),
        sa.CheckConstraint("confidence between 1 and 5", name=op.f("ck_reflections_confidence")),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["positions.id"],
            name=op.f("fk_reflections_position_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("position_id", name=op.f("pk_reflections")),
    )


def downgrade() -> None:
    op.drop_table("reflections")
    op.drop_table("journal_entries")
    op.drop_index("ix_attachments_position_id", table_name="attachments")
    op.drop_table("attachments")
    op.drop_index("ix_sync_runs_account_id", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index("ix_positions_account_id_symbol_norm", table_name="positions")
    op.drop_index("ix_positions_account_id_close_time", table_name="positions")
    op.drop_table("positions")
    op.drop_index("ix_deals_account_id_time_utc", table_name="deals")
    op.drop_index("ix_deals_account_id_position_id", table_name="deals")
    op.drop_table("deals")
    op.drop_table("account_credentials")
    op.drop_index(
        "uq_trading_accounts_mt5_identity",
        table_name="trading_accounts",
        postgresql_where=sa.text("platform = 'mt5'"),
    )
    op.drop_table("trading_accounts")
    op.drop_table("tags")
    op.drop_table("sessions")
    op.drop_table("users")
    op.drop_table("symbols")
    op.drop_index("ix_otp_codes_email_created_at", table_name="otp_codes")
    op.drop_table("otp_codes")

    # Последним и без CASCADE: если citext держит чужой объект, откат обязан упасть,
    # а не утащить за собой чужие колонки.
    op.execute("DROP EXTENSION IF EXISTS citext")
