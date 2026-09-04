"""Ротация `MASTER_KEY`. Запускается через `scripts/rotate_master_key.py`.

Перешифровывается только `wrapped_data_key` — короткое поле. `ciphertext` не читается
и не переписывается вовсе, и `updated_at` не трогается: ротация меняет ключ, а не credentials.

Порядок для оператора:

1. Сгенерировать новый ключ — 32 случайных байта в base64:
   `python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"`
2. В окружении: `MASTER_KEY_PREVIOUS` = старый ключ, `MASTER_KEY` = новый,
   `MASTER_KEY_VERSION` = прежнее значение + 1. Перезапустить API — с этого момента он
   пишет новые строки новым ключом и по-прежнему читает старые.
3. Прогнать скрипт до «осталось: 0».
4. Только после этого убрать `MASTER_KEY_PREVIOUS`.

Обрыв на любом шаге безопасен: каждая пачка коммитится отдельно, и до шага 4 обе версии
строк читаются. Повторный запуск доводит начатое до конца.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import ConfigError, get_settings
from app.core.db import dispose_engine, get_session_factory
from app.core.logging import configure_logging
from app.core.security import (
    CredentialsDecryptionError,
    CredentialsKeyError,
    MasterKeyring,
    master_keyring,
    rewrap_data_key,
)
from app.domains.accounts.models import AccountCredential

DEFAULT_BATCH_SIZE = 200

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_FAILED = 3

KEEP_MASTER_KEY = (
    "⚠️  MASTER_KEY терять нельзя: без него credentials счетов не восстанавливаются ничем."
)
KEEP_PREVIOUS = (
    "MASTER_KEY_PREVIOUS убирать из окружения только после прогона, сообщившего «осталось: 0»."
)


@dataclass(frozen=True)
class RotationReport:
    """Счётчики прогона. Ключей и открытого текста здесь нет и быть не может."""

    target_version: int
    rewrapped: int = 0
    remaining: int = 0

    @property
    def done(self) -> bool:
        return self.remaining == 0


class RotationError(RuntimeError):
    """Ротация невозможна или прервана на конкретной строке."""


async def count_pending(session: AsyncSession, target_version: int) -> int:
    stale = select(func.count()).select_from(AccountCredential)
    result = await session.execute(stale.where(AccountCredential.key_version != target_version))
    return int(result.scalar_one())


async def rotate_master_key(
    session_factory: async_sessionmaker[AsyncSession],
    keyring: MasterKeyring,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    on_batch: Callable[[RotationReport], None] | None = None,
) -> RotationReport:
    """Перешифровывает обёртки всех строк, чья версия отличается от текущей.

    Пачка = транзакция. Падение внутри пачки откатывает её целиком, ранее закоммиченные
    остаются перешифрованными — и те и другие читаются, пока `MASTER_KEY_PREVIOUS` задан.
    `on_batch` вызывается после коммита каждой пачки: там же тесты изображают обрыв.
    """
    target = keyring.current.version
    if batch_size < 1:
        raise RotationError("Размер пачки должен быть положительным")
    report = RotationReport(target_version=target)
    while True:
        async with session_factory() as session:
            async with session.begin():
                rewrapped = await _rotate_batch(session, keyring, batch_size)
            remaining = await count_pending(session, target)
        report = RotationReport(
            target_version=target,
            rewrapped=report.rewrapped + rewrapped,
            remaining=remaining,
        )
        if rewrapped == 0:
            return report
        if on_batch is not None:
            on_batch(report)


async def _rotate_batch(session: AsyncSession, keyring: MasterKeyring, batch_size: int) -> int:
    target = keyring.current.version
    rows = (
        await session.execute(
            select(
                AccountCredential.account_id,
                AccountCredential.wrapped_data_key,
                AccountCredential.key_version,
            )
            .where(AccountCredential.key_version != target)
            .order_by(AccountCredential.account_id)
            .limit(batch_size)
            # Без FOR UPDATE параллельная запись credentials (S1-06) могла бы затереть
            # перешифрованную обёртку своей, обёрнутой уже текущим ключом, — но с чужой
            # версией в колонке.
            .with_for_update()
        )
    ).all()
    for account_id, wrapped, key_version in rows:
        try:
            fresh = rewrap_data_key(wrapped, key_version, account_id=account_id, keyring=keyring)
        except CredentialsDecryptionError as exc:
            # Ни одного ключа, которым эта строка открывается. Останавливаемся: дальше
            # можно только испортить. account_id — идентификатор, не секрет.
            raise RotationError(
                f"Строка счёта {account_id} не открывается ни MASTER_KEY, ни MASTER_KEY_PREVIOUS. "
                "Ротация остановлена, изменения этой пачки откачены."
            ) from exc
        await session.execute(
            update(AccountCredential)
            .where(AccountCredential.account_id == account_id)
            # updated_at не трогаем: содержимое credentials не менялось.
            .values(wrapped_data_key=fresh.wrapped_data_key, key_version=fresh.key_version)
        )
    return len(rows)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rotate_master_key",
        description="Ротация MASTER_KEY: перешифровывает обёртки data_key, ciphertext не трогает.",
        epilog=f"{KEEP_PREVIOUS} {KEEP_MASTER_KEY}",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"строк в одной транзакции (по умолчанию {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="только посчитать строки со старой версией ключа, ничего не менять",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Точка входа CLI. В stdout — только счётчики и версии, значений ключей там нет."""
    args = _parse_args(argv)
    try:
        settings = get_settings()
    except ConfigError as exc:
        print(str(exc))
        return EXIT_CONFIG
    configure_logging(secret_values=settings.scrubbable_secret_values())
    try:
        keyring = master_keyring(settings)
    except CredentialsKeyError as exc:
        print(str(exc))
        return EXIT_CONFIG
    if keyring.previous is None:
        print(
            "MASTER_KEY_PREVIOUS не задан — расшифровать строки старой версии нечем.\n"
            "Задай переменную окружения (не аргументом командной строки: аргументы видны "
            "в списке процессов и в истории shell) и подними MASTER_KEY_VERSION."
        )
        return EXIT_CONFIG
    print(
        f"Ротация: версия ключа {keyring.previous.version} -> {keyring.current.version}. "
        "Перешифровываются только обёртки data_key, ciphertext не читается."
    )
    try:
        return asyncio.run(_run(keyring, batch_size=args.batch_size, dry_run=args.dry_run))
    finally:
        print(KEEP_MASTER_KEY)


async def _run(keyring: MasterKeyring, *, batch_size: int, dry_run: bool) -> int:
    session_factory = get_session_factory()
    try:
        if dry_run:
            async with session_factory() as session:
                pending = await count_pending(session, keyring.current.version)
            print(f"Проверка без изменений. Строк со старой версией ключа: {pending}.")
            return EXIT_OK
        try:
            report = await rotate_master_key(
                session_factory, keyring, batch_size=batch_size, on_batch=_print_progress
            )
        except RotationError as exc:
            print(str(exc))
            return EXIT_FAILED
        print(f"Перешифровано строк: {report.rewrapped}. Осталось: {report.remaining}.")
        print(KEEP_PREVIOUS if report.done else "Прогон не завершён — запусти скрипт ещё раз.")
        return EXIT_OK if report.done else EXIT_FAILED
    finally:
        await dispose_engine()


def _print_progress(report: RotationReport) -> None:
    print(f"  перешифровано: {report.rewrapped}, осталось: {report.remaining}")
