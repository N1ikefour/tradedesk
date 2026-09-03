"""Миграция ядра против настоящего Postgres (S0-03).

Схема проверяется по `information_schema` и системным каталогам, а не по моделям:
иначе тест сверял бы модели с моделями и любое общее расхождение со `SPEC.md` 3 прошло бы мимо.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.community.postgres import PostgresContainer

from alembic import command
from app.core.db import Base, get_engine
from app.core.ids import uuid7
from app.domains.accounts.models import TradingAccount
from app.domains.auth.models import User
from app.domains.ingest.models import Position
from app.domains.journal.models import Attachment, JournalEntry, Reflection

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[2]

# SPEC.md 3 целиком, кроме daily_stats: она создаётся в S2-05.
EXPECTED_COLUMNS: dict[str, dict[str, str]] = {
    "account_credentials": {
        "account_id": "uuid not null",
        "ciphertext": "bytea not null",
        "wrapped_data_key": "bytea not null",
        "key_version": "int2 not null",
        "updated_at": "timestamptz not null",
    },
    "attachments": {
        "id": "uuid not null",
        "position_id": "uuid not null",
        "s3_key": "text not null",
        "content_type": "text not null",
        "width": "int4 null",
        "height": "int4 null",
        "size_bytes": "int4 null",
        "created_at": "timestamptz not null",
    },
    "deals": {
        "id": "int8 not null",
        "account_id": "uuid not null",
        "deal_ticket": "int8 not null",
        "order_ticket": "int8 null",
        "position_id": "int8 not null",
        "symbol_raw": "text not null",
        "deal_type": "text not null",
        "entry": "text not null",
        "reason": "text null",
        "volume": "numeric(18,8) not null",
        "price": "numeric(18,8) not null",
        "profit": "numeric(18,2) not null",
        "commission": "numeric(18,2) not null",
        "swap": "numeric(18,2) not null",
        "fee": "numeric(18,2) not null",
        "time_utc": "timestamptz not null",
        "time_server": "timestamptz not null",
        "comment": "text null",
        "magic": "int8 null",
        "raw": "jsonb not null",
        "source": "text not null",
        "ingested_at": "timestamptz not null",
    },
    "journal_entries": {
        "position_id": "uuid not null",
        "notes": "text null",
        "tags": "_text not null",
        "planned_entry": "numeric(18,8) null",
        "planned_sl": "numeric(18,8) null",
        "planned_tp": "numeric(18,8) null",
        "risk_amount": "numeric(18,2) null",
        "updated_at": "timestamptz not null",
    },
    "otp_codes": {
        "id": "uuid not null",
        "email": "citext not null",
        "code_hash": "text not null",
        "expires_at": "timestamptz not null",
        "attempts": "int2 not null",
        "consumed_at": "timestamptz null",
        "created_at": "timestamptz not null",
    },
    "positions": {
        "id": "uuid not null",
        "account_id": "uuid not null",
        "position_id": "int8 not null",
        "symbol_raw": "text not null",
        "symbol_norm": "text not null",
        "direction": "text not null",
        "status": "text not null",
        "open_time": "timestamptz not null",
        "close_time": "timestamptz null",
        "volume_opened": "numeric(18,8) not null",
        "volume_closed": "numeric(18,8) not null",
        "avg_entry_price": "numeric(18,8) not null",
        "avg_exit_price": "numeric(18,8) null",
        "gross_pnl": "numeric(18,2) not null",
        "commission": "numeric(18,2) not null",
        "swap": "numeric(18,2) not null",
        "fee": "numeric(18,2) not null",
        "net_pnl": "numeric(18,2) not null",
        "deals_count": "int4 not null",
        "duration_seconds": "int4 null",
        "close_reason": "text null",
        "is_manual": "bool not null",
        "rebuilt_at": "timestamptz not null",
    },
    "reflections": {
        "position_id": "uuid not null",
        "setup_grade": "text null",
        "execution_grade": "text null",
        "followed_plan": "bool null",
        "emotion_before": "text null",
        "emotion_during": "text null",
        "emotion_after": "text null",
        "mistakes": "_text not null",
        "confidence": "int2 null",
        "free_text": "text null",
        "filled_at": "timestamptz null",
        "updated_at": "timestamptz not null",
    },
    "sessions": {
        "id": "uuid not null",
        "user_id": "uuid not null",
        "created_at": "timestamptz not null",
        "expires_at": "timestamptz not null",
        "last_seen_at": "timestamptz null",
        "user_agent": "text null",
    },
    "symbols": {
        "id": "int4 not null",
        "raw": "text not null",
        "norm": "text not null",
        "asset_class": "text null",
        "digits": "int2 null",
        "contract_size": "numeric(18,4) null",
        "tick_size": "numeric(18,8) null",
        "source": "text not null",
    },
    "sync_runs": {
        "id": "int8 not null",
        "account_id": "uuid not null",
        "source": "text not null",
        "started_at": "timestamptz not null",
        "finished_at": "timestamptz null",
        "deals_received": "int4 null",
        "deals_new": "int4 null",
        "positions_rebuilt": "int4 null",
        "server_utc_offset_minutes": "int4 null",
        "error": "text null",
    },
    "tags": {
        "id": "uuid not null",
        "user_id": "uuid not null",
        "name": "text not null",
        "color": "text null",
    },
    "trading_accounts": {
        "id": "uuid not null",
        "user_id": "uuid not null",
        "label": "text not null",
        "is_demo": "bool not null",
        "color": "text not null",
        "platform": "text not null",
        "broker": "text null",
        "server": "text null",
        "login": "int8 null",
        "currency": "bpchar(3) not null",
        "account_type": "text null",
        "server_utc_offset_minutes": "int4 null",
        "status": "text not null",
        "status_message": "text null",
        "last_sync_at": "timestamptz null",
        "last_heartbeat_at": "timestamptz null",
        "collector_id": "text null",
        "sort_order": "int4 not null",
        "created_at": "timestamptz not null",
    },
    "users": {
        "id": "uuid not null",
        "email": "citext not null",
        "display_name": "text null",
        "timezone": "text not null",
        "day_boundary_hour": "int2 not null",
        "created_at": "timestamptz not null",
    },
}

EXPECTED_INDEXES: dict[str, set[str]] = {
    "account_credentials": {"pk_account_credentials"},
    "attachments": {"pk_attachments", "ix_attachments_position_id"},
    "deals": {
        "pk_deals",
        "uq_deals_account_id_deal_ticket",
        "ix_deals_account_id_position_id",
        "ix_deals_account_id_time_utc",
    },
    "journal_entries": {"pk_journal_entries"},
    "otp_codes": {"pk_otp_codes", "ix_otp_codes_email_created_at"},
    "positions": {
        "pk_positions",
        "uq_positions_account_id_position_id",
        "ix_positions_account_id_close_time",
        "ix_positions_account_id_symbol_norm",
    },
    "reflections": {"pk_reflections"},
    "sessions": {"pk_sessions"},
    "symbols": {"pk_symbols", "uq_symbols_raw"},
    "sync_runs": {"pk_sync_runs", "ix_sync_runs_account_id"},
    "tags": {"pk_tags", "uq_tags_user_id_name"},
    "trading_accounts": {"pk_trading_accounts", "uq_trading_accounts_mt5_identity"},
    "users": {"pk_users", "uq_users_email"},
}

# SPEC.md 3 ставит cascade ровно в четырёх местах — они и держат пользовательский слой.
EXPECTED_FK_DELETE_RULES: dict[str, str] = {
    "fk_account_credentials_account_id": "CASCADE",
    "fk_attachments_position_id": "CASCADE",
    "fk_journal_entries_position_id": "CASCADE",
    "fk_reflections_position_id": "CASCADE",
    "fk_deals_account_id": "NO ACTION",
    "fk_positions_account_id": "NO ACTION",
    "fk_sessions_user_id": "NO ACTION",
    "fk_sync_runs_account_id": "NO ACTION",
    "fk_tags_user_id": "NO ACTION",
    "fk_trading_accounts_user_id": "NO ACTION",
}

EXPECTED_CHECKS: set[str] = {
    "ck_positions_direction",
    "ck_positions_status",
    "ck_reflections_confidence",
    "ck_reflections_execution_grade",
    "ck_reflections_setup_grade",
    "ck_trading_accounts_account_type",
    "ck_trading_accounts_currency_usd",
    "ck_trading_accounts_platform",
    "ck_trading_accounts_status",
}

# Серверные дефолты не сравнивает ни compare_metadata (выключено по умолчанию),
# ни проверка колонок выше: она не читает column_default.
EXPECTED_SERVER_DEFAULTS: dict[tuple[str, str], str] = {
    ("account_credentials", "key_version"): "1",
    ("deals", "id"): "nextval('deals_id_seq'::regclass)",
    ("deals", "commission"): "0",
    ("deals", "swap"): "0",
    ("deals", "fee"): "0",
    ("deals", "ingested_at"): "now()",
    ("journal_entries", "tags"): "'{}'::text[]",
    ("otp_codes", "attempts"): "0",
    ("otp_codes", "created_at"): "now()",
    ("positions", "gross_pnl"): "0",
    ("positions", "commission"): "0",
    ("positions", "swap"): "0",
    ("positions", "fee"): "0",
    ("positions", "net_pnl"): "0",
    ("positions", "is_manual"): "false",
    ("reflections", "mistakes"): "'{}'::text[]",
    ("symbols", "id"): "nextval('symbols_id_seq'::regclass)",
    ("symbols", "source"): "'auto'::text",
    ("sync_runs", "id"): "nextval('sync_runs_id_seq'::regclass)",
    ("sync_runs", "deals_received"): "0",
    ("sync_runs", "deals_new"): "0",
    ("sync_runs", "positions_rebuilt"): "0",
    ("trading_accounts", "is_demo"): "false",
    ("trading_accounts", "currency"): "'USD'::bpchar",
    ("trading_accounts", "status"): "'pending'::text",
    ("trading_accounts", "sort_order"): "0",
    ("trading_accounts", "created_at"): "now()",
    ("users", "timezone"): "'Europe/Moscow'::text",
    ("users", "day_boundary_hour"): "0",
    ("users", "created_at"): "now()",
}


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
    # Имя с маркером _test: иначе guard из core/db.py не даст создать движок.
    with PostgresContainer("postgres:16-alpine", dbname="td_test") as container:
        yield container


@pytest.fixture(scope="module")
def live_database(postgres: PostgresContainer) -> Iterator[str]:
    url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("APP_ENV", "local")
        monkeypatch.setenv("DATABASE_URL", url)
        yield url


@pytest.fixture
def alembic_config(live_database: str) -> Config:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    return config


@pytest.fixture
def migrated(alembic_config: Config) -> Iterator[None]:
    """Каждый тест получает схему, накатанную с нуля, и оставляет БД пустой."""
    command.upgrade(alembic_config, "head")
    yield
    command.downgrade(alembic_config, "base")


@pytest.fixture
def rolled_back(alembic_config: Config) -> Iterator[None]:
    """Состояние после отката. Alembic зовётся только из синхронного кода: env.py
    поднимает свой event loop через asyncio.run, внутри работающего он падает."""
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    yield


async def _fetch(sql: str) -> list[Any]:
    async with get_engine().connect() as connection:
        result = await connection.execute(text(sql))
        return list(result.all())


def test_upgrade_and_downgrade_run_twice_without_cleanup(alembic_config: Config) -> None:
    """DoD S0-03: цикл повторяется на той же БД, без ручной чистки между прогонами."""
    for _ in range(2):
        command.upgrade(alembic_config, "head")
        command.downgrade(alembic_config, "base")

    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")


async def test_downgrade_leaves_no_tables(rolled_back: None) -> None:
    rows = await _fetch(
        "select table_name from information_schema.tables where table_schema = 'public'"
    )

    # Остаётся только служебная таблица alembic — её ведёт сам alembic.
    assert {row[0] for row in rows} == {"alembic_version"}


async def test_all_spec_tables_created(migrated: None) -> None:
    rows = await _fetch(
        "select table_name from information_schema.tables "
        "where table_schema = 'public' and table_name <> 'alembic_version'"
    )

    assert {row[0] for row in rows} == set(EXPECTED_COLUMNS)


async def test_columns_match_spec(migrated: None) -> None:
    """Каждая колонка: тип, точность и nullable ровно как в SPEC.md 3."""
    rows = await _fetch("""
        select table_name, column_name, udt_name, is_nullable,
               numeric_precision, numeric_scale, character_maximum_length
        from information_schema.columns
        where table_schema = 'public' and table_name <> 'alembic_version'
        order by table_name, ordinal_position
    """)

    actual: dict[str, dict[str, str]] = {}
    for table, column, udt, nullable, precision, scale, length in rows:
        if udt == "numeric":
            udt = f"numeric({precision},{scale})"
        elif udt in {"bpchar", "varchar"} and length:
            udt = f"{udt}({length})"
        actual.setdefault(table, {})[column] = (
            f"{udt} {'null' if nullable == 'YES' else 'not null'}"
        )

    assert actual == EXPECTED_COLUMNS


async def test_indexes_match_spec(migrated: None) -> None:
    rows = await _fetch(
        "select tablename, indexname from pg_indexes "
        "where schemaname = 'public' and tablename <> 'alembic_version'"
    )

    actual: dict[str, set[str]] = {}
    for table, index in rows:
        actual.setdefault(table, set()).add(index)

    assert actual == EXPECTED_INDEXES


async def test_mt5_identity_index_is_partial_and_unique(migrated: None) -> None:
    rows = await _fetch(
        "select indexdef from pg_indexes "
        "where schemaname = 'public' and indexname = 'uq_trading_accounts_mt5_identity'"
    )

    definition = rows[0][0]
    assert "CREATE UNIQUE INDEX" in definition
    assert "(user_id, platform, server, login)" in definition
    assert "WHERE (platform = 'mt5'::text)" in definition


async def test_foreign_key_delete_rules(migrated: None) -> None:
    rows = await _fetch("""
        select rc.constraint_name, rc.delete_rule
        from information_schema.referential_constraints rc
        join information_schema.table_constraints tc
          on tc.constraint_name = rc.constraint_name
         and tc.constraint_schema = rc.constraint_schema
        where tc.table_schema = 'public'
    """)

    assert dict(rows) == EXPECTED_FK_DELETE_RULES


async def test_check_constraints_exist(migrated: None) -> None:
    rows = await _fetch(
        "select conname from pg_constraint "
        "where contype = 'c' and connamespace = 'public'::regnamespace"
    )

    assert {row[0] for row in rows} == EXPECTED_CHECKS


async def test_server_defaults_match_spec(migrated: None) -> None:
    """`default now()`, `default 0`, `default 'USD'` — их не видит ни один тест выше."""
    rows = await _fetch("""
        select table_name, column_name, column_default
        from information_schema.columns
        where table_schema = 'public'
          and table_name <> 'alembic_version'
          and column_default is not null
    """)

    assert {(table, column): default for table, column, default in rows} == (
        EXPECTED_SERVER_DEFAULTS
    )


async def test_citext_extension_installed(migrated: None) -> None:
    rows = await _fetch("select extname from pg_extension where extname = 'citext'")

    assert rows != []


async def test_models_match_migration(migrated: None) -> None:
    """Модели и миграция расходятся молча: autogenerate следующей задачи это увидит поздно."""

    def compare(connection: Connection) -> list[Any]:
        return list(compare_metadata(MigrationContext.configure(connection), Base.metadata))

    async with get_engine().connect() as connection:
        diffs = await connection.run_sync(compare)

    assert diffs == []


async def _account(session: AsyncSession, platform: str, **overrides: Any) -> TradingAccount:
    user = User(email=f"{uuid7()}@example.test")
    session.add(user)
    await session.flush()

    account = TradingAccount(
        user_id=user.id,
        label="Тестовый счёт",
        color="#111111",
        platform=platform,
        **overrides,
    )
    session.add(account)
    await session.flush()
    return account


async def _position(session: AsyncSession, account: TradingAccount) -> Position:
    now = datetime.now(UTC)
    position = Position(
        account_id=account.id,
        position_id=1,
        symbol_raw="EURUSD.m",
        symbol_norm="EURUSD",
        direction="long",
        status="closed",
        open_time=now,
        close_time=now,
        volume_opened=Decimal("1.00000000"),
        volume_closed=Decimal("1.00000000"),
        avg_entry_price=Decimal("1.10000000"),
        deals_count=2,
        rebuilt_at=now,
    )
    session.add(position)
    await session.flush()
    return position


async def test_deleting_position_removes_user_layer(migrated: None) -> None:
    """Каскад — единственный способ, которым журнал исчезает: пересборка его не трогает."""
    async with AsyncSession(get_engine()) as session:
        account = await _account(session, "mt5", server="FTMO-Demo", login=100)
        position = await _position(session, account)
        now = datetime.now(UTC)
        session.add_all(
            [
                JournalEntry(position_id=position.id, notes="план", updated_at=now),
                Reflection(position_id=position.id, setup_grade="A", updated_at=now),
                Attachment(
                    position_id=position.id,
                    s3_key="scr/1.png",
                    content_type="image/png",
                    created_at=now,
                ),
            ]
        )
        await session.commit()

        await session.delete(position)
        await session.commit()

        for table in ("journal_entries", "reflections", "attachments"):
            count = await session.execute(text(f"select count(*) from {table}"))
            assert count.scalar_one() == 0, table


async def test_check_constraints_reject_forbidden_values(migrated: None) -> None:
    """Набор имён из теста выше не ловит ошибку в самом предикате: `currency = 'RUR'`
    или `confidence between 1 and 4` прошли бы молча. Здесь проверяется, что падает
    именно то ограничение, которое должно."""
    async with AsyncSession(get_engine()) as session:
        account = await _account(session, "mt5", server="FTMO-Demo", login=100)
        position = await _position(session, account)
        user_id, account_id, position_id = account.user_id, account.id, position.id
        await session.commit()

        now = datetime.now(UTC)

        def account_with(**overrides: Any) -> TradingAccount:
            values: dict[str, Any] = {
                "user_id": user_id,
                "label": "Счёт с запрещённым значением",
                "color": "#111111",
                "platform": "mt5",
            }
            return TradingAccount(**(values | overrides))

        def position_with(**overrides: Any) -> Position:
            values: dict[str, Any] = {
                "account_id": account_id,
                "position_id": 2,
                "symbol_raw": "EURUSD.m",
                "symbol_norm": "EURUSD",
                "direction": "long",
                "status": "closed",
                "open_time": now,
                "volume_opened": Decimal("1.00000000"),
                "volume_closed": Decimal("1.00000000"),
                "avg_entry_price": Decimal("1.10000000"),
                "deals_count": 1,
                "rebuilt_at": now,
            }
            return Position(**(values | overrides))

        def reflection_with(**overrides: Any) -> Reflection:
            values: dict[str, Any] = {"position_id": position_id, "updated_at": now}
            return Reflection(**(values | overrides))

        cases: list[tuple[str, object]] = [
            ("ck_trading_accounts_currency_usd", account_with(currency="RUR")),
            ("ck_trading_accounts_platform", account_with(platform="mt4")),
            ("ck_trading_accounts_status", account_with(status="broken")),
            ("ck_trading_accounts_account_type", account_with(account_type="both")),
            ("ck_positions_direction", position_with(direction="sideways")),
            ("ck_positions_status", position_with(status="pending")),
            ("ck_reflections_setup_grade", reflection_with(setup_grade="E")),
            ("ck_reflections_execution_grade", reflection_with(execution_grade="F")),
            ("ck_reflections_confidence", reflection_with(confidence=6)),
        ]

        for constraint, row in cases:
            with pytest.raises(IntegrityError) as error:
                session.add(row)
                await session.flush()
            assert constraint in str(error.value), constraint
            await session.rollback()


async def test_check_constraints_accept_boundary_values(migrated: None) -> None:
    """Обратная сторона: границы словарей и диапазона обязаны проходить."""
    async with AsyncSession(get_engine()) as session:
        account = await _account(session, "manual", account_type="netting")
        account.status = "archived"
        position = await _position(session, account)
        position_id = position.id
        session.add_all(
            [
                Reflection(
                    position_id=position_id,
                    setup_grade="A",
                    execution_grade="D",
                    confidence=1,
                    updated_at=datetime.now(UTC),
                )
            ]
        )
        await session.commit()

        stored = await session.execute(
            text("select confidence, setup_grade, execution_grade from reflections")
        )
        assert stored.all() == [(1, "A", "D")]


async def test_mt5_accounts_collide_on_server_and_login(migrated: None) -> None:
    async with AsyncSession(get_engine()) as session:
        first = await _account(session, "mt5", server="FTMO-Demo", login=100)

        with pytest.raises(IntegrityError):
            session.add(
                TradingAccount(
                    user_id=first.user_id,
                    label="Тот же счёт второй раз",
                    color="#222222",
                    platform="mt5",
                    server="FTMO-Demo",
                    login=100,
                )
            )
            await session.flush()


async def test_manual_accounts_do_not_collide(migrated: None) -> None:
    """Частичный индекс: у csv/manual server+login произвольны и повторяются свободно."""
    async with AsyncSession(get_engine()) as session:
        first = await _account(session, "manual", server="FTMO-Demo", login=100)
        session.add(
            TradingAccount(
                user_id=first.user_id,
                label="Второй ручной счёт",
                color="#222222",
                platform="manual",
                server="FTMO-Demo",
                login=100,
            )
        )
        await session.commit()

        count = await session.execute(text("select count(*) from trading_accounts"))
        assert count.scalar_one() == 2
