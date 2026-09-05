"""Выдача заданий коллектору и приём heartbeat — SPEC.md 5.3, 5.6.

Статусы счетов этот модуль не решает: переходы живут в `accounts.service`, рядом с
`apply_sync_result`, и здесь только вызываются. Здесь — выборка, закрепление коллектора
за счётом, расшифровка credentials и журнал доступа.

**Расшифровка credentials выполняется ровно в этом файле и больше нигде** (`CLAUDE.md`
§5). Всё, что с ней связано, собрано в `issue_assignments`, чтобы граница была одним
местом, а не свойством, которое надо проверять по всему коду.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import CredentialsDecryptionError, decrypt_credentials
from app.domains.accounts import models as account_models
from app.domains.accounts import service as accounts
from app.domains.collector.schemas import HeartbeatRequest

log = get_logger(__name__)

PASSWORD_FIELD = "password"

# Credentials не читаются — счёт бесполезен коллектору, и пользователь должен узнать об
# этом от системы, а не по тишине в журнале. Текст без подробностей: причина неудачи
# расшифровки наружу не раскрывается (S0-05).
CREDENTIALS_UNREADABLE_MESSAGE = (
    "Не удалось прочитать сохранённый пароль счёта. Введите его заново в настройках счёта."
)


@dataclass(frozen=True)
class Assignment:
    """Счёт и расшифрованный пароль к нему.

    `repr` пароля подавлен: объект живёт на пути, где любое исключение печатает кадр
    стека, а `scrub_unserializable` вырезает только **известные** секреты — пароль счёта
    в их число не входит и входить не может.
    """

    account: account_models.TradingAccount
    password: str = field(repr=False)


@dataclass(frozen=True)
class HeartbeatResult:
    accepted: int
    ignored: int


def assignable() -> ColumnElement[bool]:
    """Условие «этот счёт вообще можно отдать коллектору» — SPEC.md 5.6.

    Статус в работе: `pending`, `connected`, `needs_attention`. `paused` и `archived`
    отсеиваются здесь, и это **единственное** место, где они отсеиваются: вторая такая
    проверка сделала бы обе недоказуемыми — снятие любой из них ничего бы не сломало.

    Платформа и наличие пары сервер+логин — два разных условия, и оба остаются, хотя
    сегодня перекрываются: `AccountCreateRequest` запрещает `server` и `login` всем,
    кроме mt5, поэтому мутация, снимающая одну проверку, второй и ловится. Роли у них
    всё-таки разные. `platform = 'mt5'` — намерение: коллектор ходит только в MT5.
    `server`/`login` — физическая гарантия, на которой стоит `AssignmentResponse.issued`:
    в модели ответа они не nullable, и без неё выдача падала бы пятисоткой.

    Чей это счёт — отдельное условие у каждого вызова: `_claim` берёт ничьи,
    `issue_assignments` отдаёт свои.
    """
    return and_(
        account_models.TradingAccount.status.in_(accounts.ACTIVE_STATUSES),
        account_models.TradingAccount.platform == accounts.PLATFORM_MT5,
        account_models.TradingAccount.server.is_not(None),
        account_models.TradingAccount.login.is_not(None),
    )


async def _claim(session: AsyncSession, collector_id: str) -> list[UUID]:
    """Закрепляет ничьи счета за этим коллектором. Одним UPDATE, и это принципиально.

    Два коллектора, спросившие одновременно, приходят на одну строку: Postgres выдаёт
    блокировку строки одному, второй ждёт и **перечитывает** условие — `collector_id`
    у него уже не NULL, строка из-под UPDATE выпадает. Счёт достаётся ровно одному,
    без транзакции serializable и без ретраев. Прочитать, а потом записать из питона
    значило бы отдать один счёт обоим.

    Повторный запрос того же коллектора не меняет ничего: его счета под условие
    `IS NULL` не подходят.
    """
    statement = (
        update(account_models.TradingAccount)
        .where(account_models.TradingAccount.collector_id.is_(None), assignable())
        .values(collector_id=collector_id)
        .returning(account_models.TradingAccount.id)
    )
    return list((await session.execute(statement)).scalars().all())


async def issue_assignments(session: AsyncSession, collector_id: str) -> list[Assignment]:
    """Счета этого коллектора вместе с паролями. `GET`, который пишет в базу.

    Побочный эффект требует SPEC.md 5.6 («при выдаче `collector_id` фиксируется за
    счётом») — без него второй коллектор в сети забрал бы себе те же счета, и два
    терминала полезли бы в один брокерский аккаунт.

    Счёт, чьи credentials не читаются, из выдачи выпадает и уходит в `needs_attention`.
    Уронить весь ответ пятисоткой из-за одного счёта нельзя: остальные счета этой
    установки перестали бы синкаться заодно с ним.
    """
    await _claim(session, collector_id)
    statement = (
        select(account_models.TradingAccount, account_models.AccountCredential)
        .outerjoin(
            account_models.AccountCredential,
            account_models.AccountCredential.account_id == account_models.TradingAccount.id,
        )
        .where(account_models.TradingAccount.collector_id == collector_id, assignable())
        .order_by(
            account_models.TradingAccount.created_at,
            account_models.TradingAccount.id,
        )
    )
    rows = (await session.execute(statement)).all()

    issued: list[Assignment] = []
    unreadable: list[UUID] = []
    for account, credential in rows:
        password = _read_password(account, credential)
        if password is None:
            unreadable.append(account.id)
            account.status = accounts.STATUS_NEEDS_ATTENTION
            account.status_message = CREDENTIALS_UNREADABLE_MESSAGE
            continue
        issued.append(Assignment(account=account, password=password))
    await session.commit()

    for assignment in issued:
        # SPEC.md 5.6: доступ логируется (account_id, collector_id, время) без пароля.
        # Время добавляет структурный логгер. Одна запись на счёт, а не на запрос: это
        # журнал того, что пароль покинул систему, и «сколько раз» здесь — не агрегат.
        log.info(
            "collector.credentials_issued",
            account_id=str(assignment.account.id),
            collector_id=collector_id,
        )
    if unreadable:
        log.error(
            "collector.credentials_unreadable",
            collector_id=collector_id,
            account_ids=[str(account_id) for account_id in unreadable],
        )
    return issued


def _read_password(
    account: account_models.TradingAccount,
    credential: account_models.AccountCredential | None,
) -> str | None:
    """Открытый пароль или `None`. Ничего не логирует: здесь он в руках."""
    if credential is None:
        return None
    try:
        decrypted = decrypt_credentials(
            credential.ciphertext,
            credential.wrapped_data_key,
            credential.key_version,
            account_id=account.id,
        )
    except CredentialsDecryptionError:
        return None
    return decrypted.get(PASSWORD_FIELD)


async def apply_heartbeat(
    session: AsyncSession, payload: HeartbeatRequest, *, now: datetime | None = None
) -> HeartbeatResult:
    """Отмечает счета живыми и переводит в `needs_attention` те, о которых сообщили ошибку.

    Счета, которых нет, чужие и выведенные из работы, просто не попадают в `accepted`:
    один посторонний идентификатор в списке не должен ронять heartbeat остальных.
    Что именно делает каждое состояние — `accounts.apply_heartbeat`.
    """
    reported = {account.account_id: account for account in payload.accounts}
    if not reported:
        return HeartbeatResult(accepted=0, ignored=0)

    statement = select(account_models.TradingAccount).where(
        account_models.TradingAccount.id.in_(reported),
        accounts.collector_scope(payload.collector_id),
    )
    found = (await session.execute(statement)).scalars().all()

    accepted = 0
    for account in found:
        state = reported[account.id]
        if accounts.apply_heartbeat(account, state=state.state, message=state.message, now=now):
            accepted += 1
    await session.commit()
    return HeartbeatResult(accepted=accepted, ignored=len(reported) - accepted)
