"""Ротация MASTER_KEY против настоящего Postgres (S0-05).

Главное свойство envelope проверяется побайтово: ротация перешифровывает `wrapped_data_key`
и не трогает `ciphertext`. Остальное — про обрыв: после падения на середине строки должны
читаться и старым, и новым ключом, а повторный запуск обязан довести дело до конца.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

import pytest
from alembic.config import Config
from sqlalchemy import select
from testcontainers.community.postgres import PostgresContainer

from alembic import command
from app.core.config import get_settings
from app.core.db import dispose_engine, get_session_factory
from app.core.key_rotation import (
    EXIT_CONFIG,
    EXIT_OK,
    RotationError,
    RotationReport,
    main,
    rotate_master_key,
)
from app.core.security import (
    MasterKey,
    MasterKeyring,
    decrypt_credentials,
    encrypt_credentials,
)
from app.domains.accounts.models import AccountCredential, TradingAccount
from app.domains.auth.models import User

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[2]

KEY_V1 = bytes(range(32))
KEY_V2 = bytes(range(100, 132))
KEY_V1_B64 = base64.b64encode(KEY_V1).decode()
KEY_V2_B64 = base64.b64encode(KEY_V2).decode()

KEYRING_V1 = MasterKeyring(current=MasterKey(1, KEY_V1))
KEYRING_V2 = MasterKeyring(current=MasterKey(2, KEY_V2))
KEYRING_ROTATING = MasterKeyring(current=MasterKey(2, KEY_V2), previous=MasterKey(1, KEY_V1))

PASSWORD = "investor-пароль"
UPDATED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

# Порядок обхода — по account_id, поэтому идентификаторы заданы явно.
ACCOUNT_IDS = [UUID(f"{index:08d}-0000-7000-8000-000000000000") for index in range(6)]
BROKEN_ACCOUNT_ID = UUID("ffffffff-0000-7000-8000-000000000000")


class OperatorInterruptError(RuntimeError):
    """Оператор нажал Ctrl-C между пачками."""


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
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
def migrated(live_database: str) -> Iterator[None]:
    config = Config(str(API_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(API_DIR / "alembic"))
    command.upgrade(config, "head")
    yield
    command.downgrade(config, "base")


@pytest.fixture
def rotating_env(migrated: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Окружение на время ротации: новый ключ текущий, старый — предыдущий.

    Кэш конфигурации сбрасывается здесь, а не в общей фикстуре conftest: та объявлена
    асинхронной, а тесты CLI синхронные — `main()` поднимает свой event loop.
    """
    monkeypatch.setenv("MASTER_KEY", KEY_V2_B64)
    monkeypatch.setenv("MASTER_KEY_VERSION", "2")
    monkeypatch.setenv("MASTER_KEY_PREVIOUS", KEY_V1_B64)
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("OTP_PEPPER", "test-otp-pepper")
    monkeypatch.setenv("COLLECTOR_TOKEN", "test-collector-token")
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def _run_sync[T](factory: Callable[[], Awaitable[T]]) -> T:
    """Свой event loop для синхронного теста; движок закрывается вместе с ним.

    Пул asyncpg привязан к тому loop, в котором создан: без dispose следующий прогон
    получил бы соединения из чужого цикла.
    """

    async def runner() -> T:
        try:
            return await factory()
        finally:
            await dispose_engine()

    return asyncio.run(runner())


async def _seed(count: int = 5) -> None:
    """Счета с credentials, зашифрованными ключом версии 1."""
    async with get_session_factory()() as session, session.begin():
        for index in range(count):
            account_id = ACCOUNT_IDS[index]
            user = User(email=f"{account_id}@example.test")
            session.add(user)
            await session.flush()
            session.add(
                TradingAccount(
                    id=account_id,
                    user_id=user.id,
                    label=f"Счёт {index}",
                    color="#111111",
                    platform="mt5",
                )
            )
            await session.flush()
            stored = encrypt_credentials(
                {"password": f"{PASSWORD}-{index}"}, account_id=account_id, keyring=KEYRING_V1
            )
            session.add(
                AccountCredential(
                    account_id=account_id,
                    ciphertext=stored.ciphertext,
                    wrapped_data_key=stored.wrapped_data_key,
                    key_version=stored.key_version,
                    updated_at=UPDATED_AT,
                )
            )


class Row(NamedTuple):
    """Снимок строки. ORM-объект после закрытия сессии отсоединён — берём значения."""

    account_id: UUID
    ciphertext: bytes
    wrapped_data_key: bytes
    key_version: int
    updated_at: datetime


async def _rows() -> list[Row]:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(
                AccountCredential.account_id,
                AccountCredential.ciphertext,
                AccountCredential.wrapped_data_key,
                AccountCredential.key_version,
                AccountCredential.updated_at,
            ).order_by(AccountCredential.account_id)
        )
        return [Row(*row) for row in result.all()]


async def _add_unreadable_row() -> None:
    """Строка, которую не открывает ни один из ключей: сюда упрётся ротация."""
    async with get_session_factory()() as session, session.begin():
        user = User(email=f"{BROKEN_ACCOUNT_ID}@example.test")
        session.add(user)
        await session.flush()
        session.add(
            TradingAccount(
                id=BROKEN_ACCOUNT_ID,
                user_id=user.id,
                label="Испорченная строка",
                color="#111111",
                platform="mt5",
            )
        )
        await session.flush()
        session.add(
            AccountCredential(
                account_id=BROKEN_ACCOUNT_ID,
                ciphertext=b"\x01" + bytes(92),
                wrapped_data_key=b"\x01" + bytes(60),
                key_version=1,
                updated_at=UPDATED_AT,
            )
        )


def _decrypted(row: Row, keyring: MasterKeyring) -> dict[str, str]:
    return decrypt_credentials(
        row.ciphertext,
        row.wrapped_data_key,
        row.key_version,
        account_id=row.account_id,
        keyring=keyring,
    )


async def test_rotation_rewraps_wrappers_and_keeps_ciphertext(migrated: None) -> None:
    """Весь смысл envelope: `ciphertext` не читается и не переписывается."""
    await _seed()
    before = {row.account_id: (row.ciphertext, row.wrapped_data_key) for row in await _rows()}

    report = await rotate_master_key(get_session_factory(), KEYRING_ROTATING, batch_size=2)

    rows = await _rows()
    assert report == RotationReport(target_version=2, rewrapped=5, remaining=0)
    for row in rows:
        old_ciphertext, old_wrapper = before[row.account_id]
        assert row.ciphertext == old_ciphertext
        assert row.wrapped_data_key != old_wrapper
        assert row.key_version == 2
        # Читается уже одним новым ключом — предыдущий можно убирать.
        assert _decrypted(row, KEYRING_V2)["password"].startswith(PASSWORD)


async def test_rotation_keeps_updated_at(migrated: None) -> None:
    """`updated_at` — про содержимое credentials, а ротация его не меняла."""
    await _seed()

    await rotate_master_key(get_session_factory(), KEYRING_ROTATING)

    assert {row.updated_at for row in await _rows()} == {UPDATED_AT}


async def test_rotation_is_idempotent(migrated: None) -> None:
    """Повторный прогон не переписывает уже перешифрованные строки — байт в байт."""
    await _seed()
    await rotate_master_key(get_session_factory(), KEYRING_ROTATING)
    after_first = {row.account_id: row.wrapped_data_key for row in await _rows()}

    report = await rotate_master_key(get_session_factory(), KEYRING_ROTATING)

    assert report == RotationReport(target_version=2, rewrapped=0, remaining=0)
    assert {row.account_id: row.wrapped_data_key for row in await _rows()} == after_first


async def test_interrupted_rotation_leaves_every_row_readable(migrated: None) -> None:
    """Обрыв между пачками: часть строк новой версии, часть старой, читаются обе."""
    await _seed()

    def stop(report: RotationReport) -> None:
        raise OperatorInterruptError

    with pytest.raises(OperatorInterruptError):
        await rotate_master_key(
            get_session_factory(), KEYRING_ROTATING, batch_size=2, on_batch=stop
        )

    rows = await _rows()
    versions = sorted(row.key_version for row in rows)
    assert versions == [1, 1, 1, 2, 2]
    for row in rows:
        assert _decrypted(row, KEYRING_ROTATING)["password"].startswith(PASSWORD)

    # Повторный запуск доводит начатое до конца.
    report = await rotate_master_key(get_session_factory(), KEYRING_ROTATING, batch_size=2)
    assert report == RotationReport(target_version=2, rewrapped=3, remaining=0)
    assert {row.key_version for row in await _rows()} == {2}


async def test_failure_inside_batch_rolls_the_batch_back(migrated: None) -> None:
    """Нечитаемая строка останавливает прогон, и вся её пачка откатывается целиком."""
    await _seed(count=2)
    await _add_unreadable_row()
    before = {row.account_id: row.wrapped_data_key for row in await _rows()}

    with pytest.raises(RotationError) as excinfo:
        await rotate_master_key(get_session_factory(), KEYRING_ROTATING, batch_size=10)

    rows = await _rows()
    assert str(BROKEN_ACCOUNT_ID) in str(excinfo.value)
    assert {row.account_id: row.wrapped_data_key for row in rows} == before
    assert {row.key_version for row in rows} == {1}


def test_cli_rotates_and_prints_no_key_material(
    rotating_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Прогон настоящей CLI: в stdout только счётчики и версии."""
    _run_sync(_seed)

    exit_code = main([])

    output = capsys.readouterr().out
    assert exit_code == EXIT_OK
    assert KEY_V1_B64 not in output
    assert KEY_V2_B64 not in output
    assert PASSWORD not in output
    assert "Перешифровано строк: 5. Осталось: 0." in output
    assert "MASTER_KEY_PREVIOUS убирать" in output
    assert {row.key_version for row in _run_sync(_rows)} == {2}


def test_cli_dry_run_changes_nothing(
    rotating_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_sync(_seed)

    exit_code = main(["--dry-run"])

    assert exit_code == EXIT_OK
    assert "Строк со старой версией ключа: 5." in capsys.readouterr().out
    assert {row.key_version for row in _run_sync(_rows)} == {1}


def test_cli_refuses_without_previous_key(
    rotating_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Без MASTER_KEY_PREVIOUS расшифровать старые строки нечем — прогон не начинается."""
    rotating_env.setenv("MASTER_KEY_PREVIOUS", "")
    _run_sync(_seed)

    exit_code = main([])

    output = capsys.readouterr().out
    assert exit_code == EXIT_CONFIG
    assert "MASTER_KEY_PREVIOUS" in output
    assert {row.key_version for row in _run_sync(_rows)} == {1}


def test_cli_refuses_malformed_key(
    rotating_env: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rotating_env.setenv("MASTER_KEY", "не-base64")

    exit_code = main([])

    output = capsys.readouterr().out
    assert exit_code == EXIT_CONFIG
    assert "MASTER_KEY" in output
    assert "не-base64" not in output
