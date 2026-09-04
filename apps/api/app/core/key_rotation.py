"""Ротация `MASTER_KEY`. Запускается через `scripts/rotate_master_key.py`.

Перешифровывается только `wrapped_data_key` — короткое поле. `ciphertext` не читается
и не переписывается вовсе, и `updated_at` не трогается: ротация меняет ключ, а не credentials.

Порядок для оператора:

1. Сгенерировать новый ключ — 32 случайных байта в base64:
   `python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"`
2. В окружении: `MASTER_KEY_PREVIOUS` = старый ключ, `MASTER_KEY` = новый. Номер версии
   задавать не нужно — он выводится из самого ключа. Перезапустить API: с этого момента
   он пишет новые строки новым ключом и по-прежнему читает старые.
3. Прогнать скрипт до «осталось: 0» и успешной проверки.
4. Только после этого убрать `MASTER_KEY_PREVIOUS`.

Обрыв на любом шаге безопасен: каждая пачка коммитится отдельно, и до шага 4 обе версии
строк читаются. Повторный запуск доводит начатое до конца.

Перед тем как разрешить шаг 4, скрипт перечитывает **все** строки связкой из одного текущего
ключа. Отпечаток в колонке закрывает известную причину расхождения, проверка — неизвестные:
пока хоть одна строка не открылась, «готово» не печатается и код возврата ненулевой.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import ConfigError, get_settings
from app.core.db import dispose_engine, get_session_factory
from app.core.logging import configure_logging
from app.core.security import (
    CredentialsDecryptionError,
    CredentialsKeyError,
    MasterKeyring,
    master_key_scrub_values,
    master_keyring,
    opening_master_key,
    rewrap_data_key,
)
from app.domains.accounts.models import AccountCredential

DEFAULT_BATCH_SIZE = 200

# Страховка от вечного цикла: если пачка не продвинула ни одной строки, прогон
# останавливается сам, но верхний предел итераций нужен и на случай, которого мы не ждём.
MAX_BATCHES = 100_000

# Сколько проблемных счетов печатать поимённо, чтобы не залить экран.
MAX_REPORTED_PROBLEMS = 20

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_FAILED = 3

WRAPPER_UNREADABLE = "обёртка не открывается текущим MASTER_KEY"
FINGERPRINT_MISMATCH = "отпечаток в key_version не совпадает с открывшим ключом"

KEEP_MASTER_KEY = (
    "⚠️  MASTER_KEY терять нельзя: без него credentials счетов не восстанавливаются ничем."
)
KEEP_PREVIOUS = (
    "MASTER_KEY_PREVIOUS убирать из окружения только после прогона, сообщившего «осталось: 0» "
    "и успешную проверку."
)
KEEP_PREVIOUS_UNTIL_FIXED = (
    "MASTER_KEY_PREVIOUS НЕ УБИРАТЬ: перечисленные строки после этого станут нечитаемыми."
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


@dataclass(frozen=True)
class VerificationReport:
    """Итог проверяющего прохода: сколько строк прочитано и что с ними не так."""

    checked: int = 0
    problems: tuple[tuple[UUID, str], ...] = field(default=())

    @property
    def ok(self) -> bool:
        return not self.problems


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
    """Перешифровывает обёртки всех строк, чей отпечаток отличается от текущего ключа.

    Пачка = транзакция. Падение внутри пачки откатывает её целиком, ранее закоммиченные
    остаются перешифрованными — и те и другие читаются, пока `MASTER_KEY_PREVIOUS` задан.
    `on_batch` вызывается после коммита каждой пачки: там же тесты изображают обрыв.
    """
    target = keyring.current.version
    if batch_size < 1:
        raise RotationError("Размер пачки должен быть положительным")
    report = RotationReport(target_version=target)
    for _ in range(MAX_BATCHES):
        async with session_factory() as session:
            async with session.begin():
                advanced = await _rotate_batch(session, keyring, batch_size)
            remaining = await count_pending(session, target)
        report = RotationReport(
            target_version=target,
            rewrapped=report.rewrapped + advanced,
            remaining=remaining,
        )
        if advanced == 0:
            # Считаем продвинутые строки, а не выбранные: пачка, которая ничего не меняет,
            # иначе крутилась бы вечно.
            if remaining:
                raise RotationError(
                    f"Ротация не продвигается: строк со старым ключом {remaining}, "
                    "а последняя пачка не изменила ни одной. Прогон остановлен."
                )
            return report
        if on_batch is not None:
            on_batch(report)
    raise RotationError(f"Ротация не уложилась в {MAX_BATCHES} пачек. Прогон остановлен.")


async def verify_wrappers(
    session_factory: async_sessionmaker[AsyncSession],
    keyring: MasterKeyring,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> VerificationReport:
    """Читает обёртки всех строк заданной связкой ключей. `ciphertext` не трогает.

    Вызывается со связкой из одного текущего ключа — это ровно то состояние, в котором
    система окажется после снятия `MASTER_KEY_PREVIOUS`. Строка считается проблемной,
    если обёртка не открылась или открылась ключом с другим отпечатком, чем в колонке.
    """
    checked = 0
    problems: list[tuple[UUID, str]] = []
    cursor: UUID | None = None
    while True:
        async with session_factory() as session:
            statement = (
                select(
                    AccountCredential.account_id,
                    AccountCredential.wrapped_data_key,
                    AccountCredential.key_version,
                )
                .order_by(AccountCredential.account_id)
                .limit(batch_size)
            )
            if cursor is not None:
                statement = statement.where(AccountCredential.account_id > cursor)
            rows = (await session.execute(statement)).all()
        if not rows:
            return VerificationReport(checked=checked, problems=tuple(problems))
        for account_id, wrapped, key_version in rows:
            checked += 1
            try:
                key = opening_master_key(
                    wrapped, key_version, account_id=account_id, keyring=keyring
                )
            except CredentialsDecryptionError:
                problems.append((account_id, WRAPPER_UNREADABLE))
                continue
            if key.version != key_version:
                problems.append((account_id, FINGERPRINT_MISMATCH))
        cursor = rows[-1][0]


async def _rotate_batch(session: AsyncSession, keyring: MasterKeyring, batch_size: int) -> int:
    """Возвращает число реально изменённых строк — по `rowcount`, а не по размеру выборки."""
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
            # перешифрованную обёртку своей, обёрнутой уже текущим ключом.
            .with_for_update()
        )
    ).all()
    advanced = 0
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
        result = await session.execute(
            update(AccountCredential)
            .where(AccountCredential.account_id == account_id)
            # updated_at не трогаем: содержимое credentials не менялось.
            .values(wrapped_data_key=fresh.wrapped_data_key, key_version=fresh.key_version)
        )
        # UPDATE всегда возвращает CursorResult, но типы SQLAlchemy обещают только Result.
        advanced += cast(CursorResult[Any], result).rowcount
    return advanced


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
        help="только посчитать строки со старым ключом, ничего не менять",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Точка входа CLI. В stdout — только счётчики, отпечатки и account_id."""
    args = _parse_args(argv)
    try:
        settings = get_settings()
    except ConfigError as exc:
        print(str(exc))
        return EXIT_CONFIG
    configure_logging(
        secret_values=[*settings.scrubbable_secret_values(), *master_key_scrub_values(settings)]
    )
    try:
        keyring = master_keyring(settings)
    except CredentialsKeyError as exc:
        print(str(exc))
        return EXIT_CONFIG
    if keyring.previous is None:
        print(
            "MASTER_KEY_PREVIOUS не задан — расшифровать строки старого ключа нечем.\n"
            "Задай переменную окружения (не аргументом командной строки: аргументы видны "
            "в списке процессов и в истории shell)."
        )
        return EXIT_CONFIG
    print(
        f"Ротация: отпечаток ключа {keyring.previous.version} -> {keyring.current.version}. "
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
            print(f"Проверка без изменений. Строк со старым ключом: {pending}.")
            return EXIT_OK
        try:
            report = await rotate_master_key(
                session_factory, keyring, batch_size=batch_size, on_batch=_print_progress
            )
        except RotationError as exc:
            print(str(exc))
            return EXIT_FAILED
        print(f"Перешифровано строк: {report.rewrapped}. Осталось: {report.remaining}.")
        if not report.done:
            print("Прогон не завершён — запусти скрипт ещё раз.")
            return EXIT_FAILED
        # Связка из одного текущего ключа: ровно то, что останется после снятия PREVIOUS.
        verification = await verify_wrappers(
            session_factory, MasterKeyring(current=keyring.current), batch_size=batch_size
        )
        _print_verification(verification)
        return EXIT_OK if verification.ok else EXIT_FAILED
    finally:
        await dispose_engine()


def _print_verification(verification: VerificationReport) -> None:
    if verification.ok:
        print(f"Проверено строк: {verification.checked} — все открываются одним текущим ключом.")
        print(KEEP_PREVIOUS)
        return
    print(
        f"Проверено строк: {verification.checked}, из них проблемных: {len(verification.problems)}."
    )
    for account_id, reason in verification.problems[:MAX_REPORTED_PROBLEMS]:
        print(f"  счёт {account_id}: {reason}")
    hidden = len(verification.problems) - MAX_REPORTED_PROBLEMS
    if hidden > 0:
        print(f"  … и ещё {hidden}")
    print(KEEP_PREVIOUS_UNTIL_FIXED)


def _print_progress(report: RotationReport) -> None:
    print(f"  перешифровано: {report.rewrapped}, осталось: {report.remaining}")
