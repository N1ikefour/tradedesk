"""Выдача заданий коллектору и приём heartbeat — SPEC.md 5.3, 5.6.

Статусы счетов этот модуль не решает: переходы живут в `accounts.service`, рядом с
`apply_sync_result`, и здесь только вызываются. Здесь — выборка и закрепление коллектора
за счётом.

**Задание больше не несёт пароля** (`T-07`, ADR-0006): в терминал MT5 входит человек,
коллектор подключается к открытому. Отсюда следствие, которое стоит держать в голове при
правках этого файла: `decrypt_credentials` здесь не вызывается — и не должен. Пароль,
который никому не нужен, не обязан ни ездить по сети, ни лежать в кадрах стека
(`docs/PROJECT_CONTEXT.md`, риск 5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domains.accounts import models as account_models
from app.domains.accounts import service as accounts
from app.domains.collector.schemas import HeartbeatRequest

log = get_logger(__name__)


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
    в модели ответа они не nullable, и без неё выдача падала бы пятисоткой. `login` при
    этом стал ещё и рабочим полем: по нему коллектор сверяет, в какой счёт вошёл человек
    в открытом терминале.

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


async def issue_assignments(
    session: AsyncSession, collector_id: str
) -> list[account_models.TradingAccount]:
    """Счета этого коллектора. `GET`, который пишет в базу.

    Побочный эффект требует SPEC.md 5.6 («при выдаче `collector_id` фиксируется за
    счётом») — без него второй коллектор в сети забрал бы себе те же счета, и два
    процесса полезли бы в один брокерский аккаунт.

    Наличие сохранённого пароля на выдачу не влияет никак: счёт без credentials — норма
    с `T-07`, а не поломка. Прежняя ветка «credentials не читаются → `needs_attention`»
    убрана вместе с чтением: она объявляла бы неисправным каждый нормально заведённый
    счёт.
    """
    claimed = await _claim(session, collector_id)
    statement = (
        select(account_models.TradingAccount)
        .where(account_models.TradingAccount.collector_id == collector_id, assignable())
        .order_by(
            account_models.TradingAccount.created_at,
            account_models.TradingAccount.id,
        )
    )
    issued = list((await session.execute(statement)).scalars().all())
    await session.commit()

    if claimed:
        # Только закрепление, а не каждая выдача: секрета в ответе больше нет, и строка
        # на счёт каждую минуту была бы шумом. Записывается ровно событие «счёт достался
        # этому коллектору» — единственное, что тут вообще меняется в данных, и первое,
        # что спрашивают, когда счёт ведёт не та машина (SPEC.md 5.6).
        log.info(
            "collector.accounts_claimed",
            collector_id=collector_id,
            account_ids=[str(account_id) for account_id in claimed],
        )
    return issued


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
