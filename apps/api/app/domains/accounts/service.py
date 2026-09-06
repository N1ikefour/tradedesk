"""Счета пользователя — SPEC.md 5.2.

Три правила, из которых растёт всё остальное.

1. **Скоупинг по владельцу в каждом запросе.** Счёт достаётся только через `get_owned`,
   и чужой идентификатор даёт `404`, а не `403`: существование чужого счёта наружу не
   подтверждается (`CLAUDE.md` §2, acceptance S1-06).
2. **Пароль живёт в `account_credentials` и в пользовательский API не выходит.** Здесь
   он только пишется. Расшифровка — исключительно `GET /internal/collector/assignments`
   (S1-05), и в этом модуле `decrypt_credentials` не вызывается нигде.
3. **Архив и удаление — разные операции.** Архив забирает у счёта credentials и убирает
   его из работы, оставляя сделки. Удаление уносит счёт вместе со сделками, позициями
   и всем пользовательским слоем на этих позициях — необратимо, см. `delete_account`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.ids import uuid7
from app.core.security import encrypt_credentials
from app.core.text import sanitize_external_text
from app.domains.accounts import models
from app.domains.accounts.schemas import (
    ACCOUNT_COLORS,
    AccountCreateRequest,
    AccountUpdateRequest,
)
from app.domains.ingest import models as ingest_models

ACCOUNT_NOT_FOUND_CODE = "account_not_found"
ACCOUNT_NOT_FOUND_MESSAGE = "Счёт не найден"
ACCOUNT_EXISTS_CODE = "account_already_exists"
ACCOUNT_EXISTS_MESSAGE = "Такой счёт MT5 уже добавлен: сервер и логин совпадают"
ACCOUNT_ARCHIVED_CODE = "account_archived"
ACCOUNT_ARCHIVED_MESSAGE = "Счёт в архиве: изменить его или возобновить синк уже нельзя"
ACCOUNT_PAUSED_CODE = "account_paused"
ACCOUNT_PAUSED_MESSAGE = "Синхронизация счёта на паузе. Сначала возобновите её"
NOT_MT5_CODE = "not_mt5_account"
NOT_MT5_MESSAGE = "Сервер, логин и пароль есть только у счетов MT5"

STATUS_PENDING = "pending"
STATUS_CONNECTED = "connected"
STATUS_NEEDS_ATTENTION = "needs_attention"
STATUS_PAUSED = "paused"
STATUS_ARCHIVED = "archived"

# Статусы, в которых счёт участвует в работе: их и переключают синк, пауза и heartbeat.
# `paused` и `archived` сюда не входят намеренно — это решения пользователя, и синк,
# пришедший позже решения, не должен их отменять.
ACTIVE_STATUSES = (STATUS_PENDING, STATUS_CONNECTED, STATUS_NEEDS_ATTENTION)

# SPEC.md 9.3 и 10 называют одно и то же число: heartbeat старше 5 минут — коллектор
# не на связи.
COLLECTOR_OFFLINE_AFTER = timedelta(minutes=5)

# Состояния счёта в heartbeat коллектора (SPEC.md 5.3).
HEARTBEAT_STATE_RUNNING = "running"
HEARTBEAT_STATE_ERROR = "error"
HEARTBEAT_STATE_STOPPED = "stopped"
HEARTBEAT_STATES = (HEARTBEAT_STATE_RUNNING, HEARTBEAT_STATE_ERROR, HEARTBEAT_STATE_STOPPED)

# Текст `check_collectors` — дословно из SPEC.md 10.
COLLECTOR_OFFLINE_MESSAGE = "Коллектор не на связи"
# `state=error` без `message`: показать «красный без причины» хуже, чем сказать прямо,
# что причина не пришла.
COLLECTOR_ERROR_MESSAGE = "Коллектор сообщил об ошибке без подробностей"

PLATFORM_MT5 = "mt5"

# v1: только USD (SPEC.md 3.2, `check (currency = 'USD')`).
SUPPORTED_CURRENCY = "USD"
# Код валюты приходит от терминала и попадает в текст, который увидит пользователь.
# Берём из него только буквы и цифры и не больше короткого хвоста: сообщение об ошибке —
# не место для произвольной строки из внешнего источника.
_CURRENCY_RE = re.compile(r"[^A-Z0-9]")
CURRENCY_CODE_MAX_LENGTH = 12

# Имя частичного уникального индекса (user_id, platform, server, login) для mt5 —
# по нему отличается «дубль счёта» от любого другого нарушения целостности.
MT5_IDENTITY_INDEX = "uq_trading_accounts_mt5_identity"

# Поля, смена которых заставляет коллектор входить в терминал заново.
CREDENTIAL_IDENTITY_FIELDS = ("server", "login")
MT5_ONLY_FIELDS = ("server", "login", "password")


def not_found() -> ApiError:
    return ApiError(ACCOUNT_NOT_FOUND_CODE, ACCOUNT_NOT_FOUND_MESSAGE, status_code=404)


def _already_exists() -> ApiError:
    return ApiError(ACCOUNT_EXISTS_CODE, ACCOUNT_EXISTS_MESSAGE, status_code=409)


def _archived() -> ApiError:
    return ApiError(ACCOUNT_ARCHIVED_CODE, ACCOUNT_ARCHIVED_MESSAGE, status_code=422)


def _paused() -> ApiError:
    return ApiError(ACCOUNT_PAUSED_CODE, ACCOUNT_PAUSED_MESSAGE, status_code=422)


def _not_mt5() -> ApiError:
    return ApiError(NOT_MT5_CODE, NOT_MT5_MESSAGE, status_code=422)


def _now() -> datetime:
    return datetime.now(UTC)


def unsupported_currency_message(currency: str | None) -> str | None:
    """Текст для `status_message`, если счёт открыт не в USD. `None` — валюта подходит.

    Живёт в домене счетов, а не в ингесте: см. `apply_sync_result`.
    """
    if currency is None:
        return None
    code = _CURRENCY_RE.sub("", currency.strip().upper())[:CURRENCY_CODE_MAX_LENGTH]
    if not code or code == SUPPORTED_CURRENCY:
        return None
    return (
        f"Счёт открыт в валюте {code}, а эта версия работает только со счетами в USD. "
        "Сделки сохраняются, но суммы в журнале и статистике считать по ним нельзя."
    )


def _positions_count_column() -> ColumnElement[int]:
    """Коррелированный подзапрос: счётчик позиций считается тем же запросом, что и список.

    Отдельным запросом на счёт это был бы N+1 на экране, который открывается первым.
    """
    return (
        select(func.count())
        .select_from(ingest_models.Position)
        .where(ingest_models.Position.account_id == models.TradingAccount.id)
        .correlate(models.TradingAccount)
        .scalar_subquery()
        .label("positions_count")
    )


async def list_accounts(
    session: AsyncSession, user_id: UUID, *, include_archived: bool = False
) -> list[tuple[models.TradingAccount, int]]:
    """Счета пользователя вместе со счётчиком позиций.

    Порядок детерминированный: `sort_order` у всех новых счетов один и тот же (0), и без
    вторичных ключей две загрузки одного экрана давали бы разный порядок карточек.
    """
    statement = (
        select(models.TradingAccount, _positions_count_column())
        .where(models.TradingAccount.user_id == user_id)
        .order_by(
            models.TradingAccount.sort_order,
            models.TradingAccount.created_at,
            models.TradingAccount.id,
        )
    )
    if not include_archived:
        statement = statement.where(models.TradingAccount.status != STATUS_ARCHIVED)
    rows = (await session.execute(statement)).all()
    return [(row[0], row[1]) for row in rows]


async def get_owned(
    session: AsyncSession, user_id: UUID, account_id: UUID
) -> models.TradingAccount:
    """Счёт этого пользователя. Чужой и несуществующий неотличимы: оба — 404."""
    statement = select(models.TradingAccount).where(
        models.TradingAccount.id == account_id,
        models.TradingAccount.user_id == user_id,
    )
    account = (await session.execute(statement)).scalar_one_or_none()
    if account is None:
        raise not_found()
    return account


async def positions_count(session: AsyncSession, account_id: UUID) -> int:
    statement = (
        select(func.count())
        .select_from(ingest_models.Position)
        .where(ingest_models.Position.account_id == account_id)
    )
    return (await session.execute(statement)).scalar_one()


async def _next_color(session: AsyncSession, user_id: UUID) -> str:
    """Первый цвет палитры, не занятый живыми счетами пользователя.

    Когда палитра исчерпана, цвета начинают повторяться — это лучше, чем отказ добавить
    девятый счёт: цвет здесь помогает различать, а не идентифицирует.
    """
    statement = select(models.TradingAccount.color).where(
        models.TradingAccount.user_id == user_id,
        models.TradingAccount.status != STATUS_ARCHIVED,
    )
    used = set((await session.execute(statement)).scalars().all())
    for color in ACCOUNT_COLORS:
        if color not in used:
            return color
    return ACCOUNT_COLORS[len(used) % len(ACCOUNT_COLORS)]


def _is_duplicate_mt5_identity(error: IntegrityError) -> bool:
    """Отличает дубль счёта от любого другого нарушения целостности.

    Проверяется имя индекса, а не текст ошибки целиком: превращать в «счёт уже добавлен»
    падение по чужому ограничению значило бы скрыть настоящую поломку.
    """
    return MT5_IDENTITY_INDEX in f"{error.orig}{error}"


async def create_account(
    session: AsyncSession, user_id: UUID, payload: AccountCreateRequest
) -> models.TradingAccount:
    """Создаёт счёт со статусом `pending`; для mt5 сразу шифрует пароль.

    Идентификатор генерируется до шифрования не для красоты: `account_id` входит в AAD
    обоих слоёв конверта (S0-05), поэтому шифровать нечем, пока его нет.
    """
    account_id = uuid7()
    account = models.TradingAccount(
        id=account_id,
        user_id=user_id,
        label=payload.label,
        is_demo=payload.is_demo,
        color=payload.color or await _next_color(session, user_id),
        platform=payload.platform,
        broker=payload.broker,
        server=payload.server,
        login=payload.login,
        currency=SUPPORTED_CURRENCY,
        status=STATUS_PENDING,
        sort_order=payload.sort_order,
    )
    session.add(account)
    try:
        # Явный flush до записи credentials: у них внешний ключ на этот счёт, а строка
        # ещё не в базе. Заодно дубль mt5 всплывает здесь, а не посреди commit.
        await session.flush()
        if payload.password is not None:
            await _store_credentials(session, account_id, payload.password.get_secret_value())
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        if _is_duplicate_mt5_identity(error):
            raise _already_exists() from None
        raise
    return account


async def _store_credentials(session: AsyncSession, account_id: UUID, password: str) -> None:
    """Пишет пароль в `account_credentials`, перезаписывая предыдущий.

    UPSERT, а не delete+insert: строка одна на счёт, и промежуточного состояния «пароля
    нет» у работающего счёта быть не должно.
    """
    encrypted = encrypt_credentials({"password": password}, account_id=account_id)
    statement = pg_insert(models.AccountCredential).values(
        account_id=account_id,
        ciphertext=encrypted.ciphertext,
        wrapped_data_key=encrypted.wrapped_data_key,
        key_version=encrypted.key_version,
        updated_at=_now(),
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[models.AccountCredential.account_id],
            set_={
                "ciphertext": statement.excluded.ciphertext,
                "wrapped_data_key": statement.excluded.wrapped_data_key,
                "key_version": statement.excluded.key_version,
                "updated_at": statement.excluded.updated_at,
            },
        )
    )


def _resets_connection(account: models.TradingAccount, changes: dict[str, Any]) -> bool:
    """Требует ли правка нового входа коллектора в терминал.

    Пароль — да, всегда: его набирают заново только потому, что старый не подошёл.
    `server` и `login` — только если значение **изменилось**. Разница принципиальная:
    форма редактирования шлёт карточку целиком, и «присутствует в теле» означало бы, что
    переименование счёта каждый раз роняет работающий синк в `pending`.
    """
    if "password" in changes:
        return True
    return any(
        name in changes and getattr(account, name) != changes[name]
        for name in CREDENTIAL_IDENTITY_FIELDS
    )


async def update_account(
    session: AsyncSession, account: models.TradingAccount, payload: AccountUpdateRequest
) -> models.TradingAccount:
    """Частичная правка. Архивный счёт не меняется — 422."""
    if account.status == STATUS_ARCHIVED:
        raise _archived()
    changes = payload.model_dump(exclude_unset=True)
    if account.platform != PLATFORM_MT5 and any(name in changes for name in MT5_ONLY_FIELDS):
        raise _not_mt5()

    resets = _resets_connection(account, changes)
    password = changes.pop("password", None)
    for field, value in changes.items():
        setattr(account, field, value)
    if password is not None:
        await _store_credentials(session, account.id, password.get_secret_value())
    if resets:
        # Пауза переживает смену пароля: возобновление синка — отдельное решение
        # пользователя, и молча возвращать счёт в работу правкой формы нельзя.
        if account.status != STATUS_PAUSED:
            account.status = STATUS_PENDING
        # Причина прошлого `needs_attention` относилась к прежним credentials.
        account.status_message = None
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        if _is_duplicate_mt5_identity(error):
            raise _already_exists() from None
        raise
    return account


async def set_paused(
    session: AsyncSession, account: models.TradingAccount, *, paused: bool
) -> models.TradingAccount:
    """`paused` ↔ `pending` (SPEC.md 5.2). Идемпотентно: повтор ничего не меняет.

    Возобновление возвращает счёт в `pending`, а не в прежний статус: `connected` значит
    «синк был только что», и восстанавливать это утверждение из памяти нельзя — его
    подтвердит первый же успешный синк.
    """
    if account.status == STATUS_ARCHIVED:
        raise _archived()
    target = STATUS_PAUSED if paused else STATUS_PENDING
    if paused and account.status == STATUS_PAUSED:
        return account
    if not paused and account.status != STATUS_PAUSED:
        return account
    account.status = target
    account.status_message = None
    await session.commit()
    return account


async def archive_account(
    session: AsyncSession, account: models.TradingAccount
) -> models.TradingAccount:
    """Убирает счёт из работы и **удаляет его credentials**. Сделки остаются.

    Пароль стирается, а не просто перестаёт выдаваться: архивный счёт никто не открывает,
    и хранить для него расшифровываемый пароль — держать секрет без единого потребителя.
    Идемпотентно: повторный архив — тот же ответ.
    """
    await session.execute(
        delete(models.AccountCredential).where(models.AccountCredential.account_id == account.id)
    )
    account.status = STATUS_ARCHIVED
    # Причина `needs_attention` больше не актуальна: счёт выведен из работы.
    account.status_message = None
    await session.commit()
    return account


async def delete_account(session: AsyncSession, account: models.TradingAccount) -> None:
    """Полное удаление счёта (SPEC.md 5.2). **Необратимо и уносит пользовательский слой.**

    Вместе со счётом исчезают его `deals`, `positions`, `sync_runs`, а вместе с позициями
    — `journal_entries`, `reflections` и `attachments` (у них `on delete cascade` на
    `positions.id`). `CLAUDE.md` §2 защищает этот слой от **пересборки позиций**, а не от
    явного удаления счёта: здесь пользователь сказал «удалить счёт», и оставить висеть
    заметки без позиций было бы не сохранностью, а мусором. На фронте операция
    подтверждается вводом имени счёта (SPEC.md 5.2).

    Внешние ключи `deals`, `positions` и `sync_runs` на `trading_accounts` объявлены без
    `on delete cascade` (S0-03), поэтому порядок здесь явный: сначала дети, потом счёт.
    `account_credentials` уходит своим каскадом.

    ⚠️ Файлы вложений в S3 этим не удаляются — их чистка появится вместе с самим
    хранилищем в S2-04; сейчас таблица пуста, писать в неё ещё нечему.
    """
    await session.execute(
        delete(ingest_models.Position).where(ingest_models.Position.account_id == account.id)
    )
    await session.execute(
        delete(ingest_models.Deal).where(ingest_models.Deal.account_id == account.id)
    )
    await session.execute(
        delete(ingest_models.SyncRun).where(ingest_models.SyncRun.account_id == account.id)
    )
    await session.execute(
        delete(models.TradingAccount).where(models.TradingAccount.id == account.id)
    )
    await session.commit()


def is_collector_online(account: models.TradingAccount, *, now: datetime | None = None) -> bool:
    """Свежий ли heartbeat. Порог тот же, по которому `check_collectors()` (SPEC.md 10)
    уводит счёт в `needs_attention`, и по которому экран счетов (SPEC.md 9.3) показывает
    «коллектор не на связи»: три разных ответа на один вопрос разошлись бы неизбежно.
    """
    if account.last_heartbeat_at is None:
        return False
    return (now or _now()) - account.last_heartbeat_at <= COLLECTOR_OFFLINE_AFTER


def collector_scope(collector_id: str) -> ColumnElement[bool]:
    """Счета, которые видит этот коллектор: закреплённые за ним и ничьи (SPEC.md 5.6).

    То же правило, по которому assignments решает, что отдать, — но там оно исполняется
    закреплением: ничей счёт становится своим прямо в выдаче. Здесь закрепления нет,
    heartbeat ничего не присваивает, поэтому «ничей» остаётся в области видимости.

    Чужой счёт под это условие не подходит ни в одном из двух маршрутов: коллектор,
    которому счёт не выдавали, не может и переключить ему статус.
    """
    return or_(
        models.TradingAccount.collector_id.is_(None),
        models.TradingAccount.collector_id == collector_id,
    )


async def request_sync(session: AsyncSession, account: models.TradingAccount) -> datetime:
    """Ставит `sync_requested_at`; синк выполняет коллектор (SPEC.md 5.2, 8.2).

    Пауза и архив — 422, а не молчаливое «принято»: в обоих случаях счёта нет в выдаче
    `GET /internal/collector/assignments` (SPEC.md 5.6), то есть просьбу физически некому
    прочитать, и `202` был бы обещанием, которого система не выполнит.

    Повторный вызов просто двигает метку вперёд. Отдельного «уже запрошено» нет намеренно:
    коллектор сравнивает метку с последним синком, и более поздняя просьба — не конфликт.
    """
    if account.status == STATUS_ARCHIVED:
        raise _archived()
    if account.status == STATUS_PAUSED:
        raise _paused()
    requested_at = _now()
    account.sync_requested_at = requested_at
    await session.commit()
    return requested_at


async def list_sync_runs(
    session: AsyncSession, account_id: UUID, *, limit: int
) -> Sequence[ingest_models.SyncRun]:
    """Последние прогоны синка, новые сверху (SPEC.md 5.2 — «последние 50»)."""
    statement = (
        select(ingest_models.SyncRun)
        .where(ingest_models.SyncRun.account_id == account_id)
        .order_by(ingest_models.SyncRun.started_at.desc(), ingest_models.SyncRun.id.desc())
        .limit(limit)
    )
    return (await session.execute(statement)).scalars().all()


def apply_sync_result(
    account: models.TradingAccount,
    *,
    currency: str | None = None,
    margin_mode: str | None = None,
    server_utc_offset_minutes: int | None = None,
    synced_at: datetime | None = None,
) -> None:
    """Что синк меняет в карточке счёта. Единственная точка — её зовёт `POST /ingest/deals`.

    **Здесь же живёт проверка валюты, и это осознанное решение S1-06.** `account_info`
    приходит с ингестом (SPEC.md 5.3), но проверять валюту в ингесте нельзя: там же
    выставляется `status='connected'`, и две половины одного решения, разнесённые по
    доменам, расходятся при первом рефакторинге. Счёт в евро получил бы «подключён»,
    а суммы поехали бы без единого внешнего признака — ровно тот дефект, который не
    видно ни в UI, ни в логах. Пока обе ветки статуса стоят в одной функции, забыть
    вторую невозможно.

    Валюта счёта в БД при этом **не переписывается**: колонка закрыта
    `check (currency = 'USD')` (SPEC.md 3.2), и «сохранить как есть» здесь означало бы
    отказ всей транзакции ингеста вместо понятного предупреждения.

    Не коммитит: ингест выполняет батч одной транзакцией (SPEC.md 5.3, пункт 4).
    """
    account.last_sync_at = synced_at or _now()
    if server_utc_offset_minutes is not None:
        account.server_utc_offset_minutes = server_utc_offset_minutes
    if margin_mode in models.ACCOUNT_TYPES:
        account.account_type = margin_mode
    if account.status not in ACTIVE_STATUSES:
        return
    problem = unsupported_currency_message(currency)
    if problem is not None:
        account.status = STATUS_NEEDS_ATTENTION
        account.status_message = problem
        return
    account.status = STATUS_CONNECTED
    account.status_message = None


def apply_heartbeat(
    account: models.TradingAccount,
    *,
    state: str,
    message: str | None = None,
    now: datetime | None = None,
) -> bool:
    """Что heartbeat коллектора меняет в карточке счёта (SPEC.md 5.3).

    Возвращает `False`, если счёт вне работы: `paused` и `archived` — решения
    пользователя, и heartbeat не трогает у них **ничего**, включая `last_heartbeat_at`.
    Эта проверка здесь единственная: продублируй её ещё и в выборке маршрута — и обе
    станут недоказуемыми, потому что снятие любой из них ничего не сломает.

    **Heartbeat никогда не ставит `connected`.** Каждый переход статуса имеет ровно
    одного производителя, иначе двое начинают спорить о состоянии счёта:

    | Переход | Кто |
    |---|---|
    | → `connected` | `apply_sync_result` — только успешный синк вправе это утверждать |
    | активный → `needs_attention` по ошибке коллектора | `apply_heartbeat` |
    | `connected` → `needs_attention` по молчанию | `check_collectors` |
    | → `pending` | создание, `resume`, смена credentials |
    | → `paused`, `archived` | пользователь |

    Отсюда же ответ на «кто возвращает счёт из `needs_attention`»: синк, и только он.
    Живой процесс коллектора доказывает, что процесс жив, а не что счёт синкается, —
    и не знает о причинах, которые ставил не он. Счёт в евро (`apply_sync_result`)
    иначе мигал бы между `needs_attention` и `connected` каждую минуту.

    `state='stopped'` статус не меняет: остановленный процесс — это штатное выключение,
    а не поломка. Молчание такого счёта через пять минут подберёт `check_collectors`.

    Не коммитит: heartbeat обрабатывает весь список счетов одной транзакцией.
    """
    if account.status not in ACTIVE_STATUSES:
        return False
    account.last_heartbeat_at = now or _now()
    if state == HEARTBEAT_STATE_ERROR:
        account.status = STATUS_NEEDS_ATTENTION
        # X-21: текст пришёл извне и уедет на все экраны через AccountResponse.
        account.status_message = sanitize_external_text(message) or COLLECTOR_ERROR_MESSAGE
    return True


async def check_collectors(session: AsyncSession, *, now: datetime | None = None) -> list[UUID]:
    """Счета, чей коллектор замолчал, уводит в `needs_attention` (SPEC.md 10).

    Задача arq по расписанию раз в минуту. Планировщик живёт отдельно — `app/worker.py`
    (`X-25`), он и зовёт это из обёртки, которая открывает сессию. Здесь функция остаётся
    обычной async-функцией от сессии: переход статуса проверяется без очереди и redis.

    `last_heartbeat_at IS NULL` не попадает под условие, и это важно: счёт, которому
    коллектор никогда не отвечал, — это CSV или советник (SPEC.md 5.3), и сказать про
    него «коллектор не на связи» было бы неправдой. SQL отсекает NULL сам, сравнение
    с ним неистинно; SPEC.md 10 говорит ровно то же словами «с `last_heartbeat_at`
    старше 5 мин».

    Возвращает идентификаторы затронутых счетов — их печатает вызывающий, и по ним же
    считается «сколько ушло в offline» без второго запроса.
    """
    threshold = (now or _now()) - COLLECTOR_OFFLINE_AFTER
    statement = (
        update(models.TradingAccount)
        .where(
            models.TradingAccount.status == STATUS_CONNECTED,
            models.TradingAccount.last_heartbeat_at < threshold,
        )
        .values(status=STATUS_NEEDS_ATTENTION, status_message=COLLECTOR_OFFLINE_MESSAGE)
        .returning(models.TradingAccount.id)
    )
    affected = list((await session.execute(statement)).scalars().all())
    await session.commit()
    return affected
