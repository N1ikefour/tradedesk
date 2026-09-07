"""Приём батча сделок и пересборка позиций — SPEC.md 5.3.

Шов, в котором готовые по отдельности части впервые складываются в путь «данные брокера →
строки в базе»: контракт (`schemas.py`), нормализация (`normalizer.py`), словарь символов
(`symbol_registry.py`) и сборщик (`position_builder.py`). Здесь появляется всё, чего у них
нет: транзакция, повторы и чужие строки.

Пять решений этого модуля видны снаружи.

1. **Батч — одна транзакция, и при отказе она откатывается целиком.** Так требует §5.3
   пункт 4 («пересборка в той же транзакции»), и полный откат безопасен ровно потому, что
   вставка идемпотентна: коллектор перезапрашивает окно `last_sync_at − 24h` (§8.2), и
   откаченный батч приедет снова. Частичный успех был бы хуже отказа: часть сделок в базе,
   позиции по ним не пересобраны, и никакого признака этого в данных нет.
2. **Позиция собирается по всем сделкам счёта, а не по пришедшим в батче.** Комиссия по
   позиции (`other` с ненулевым `position_id`) приезжает следующим окном синка, когда
   торговые сделки уже лежат в базе; собери мы по батчу — группа из одних корректировок
   отвергается сборщиком, и позиция теряет деньги молча. Поэтому после вставки сделки
   **перечитываются из базы** по затронутым `position_id`.
3. **Группа, которая не складывается в позицию, не роняет батч.** Сборщик отказывается
   (`PositionBuildError`), когда у группы нет ни одного входа: окно синка перезапрашивает
   сутки, и группа из одних выходов или одних корректировок теоретически возможна раньше,
   чем приедет вход. Сделки при этом уже сохранены (они факты брокера), поэтому отказ по
   такой группе — событие лога `ingest.position_unbuildable`, а не 500 на весь счёт: вход
   приедет следующим батчем, и позиция соберётся сама.
4. **`ensure_symbols` зовётся по символам собранных позиций, а не по сделкам батча.**
   У неторговой операции символ пуст (`X-44`), и наивный вызов по всем сделкам завёл бы в
   `symbols` строку с пустым `raw` — инструмент-призрак, ровно то, ради чего в `X-44`
   отвергли заполнитель. Символ собранной позиции взят сборщиком у сделки входа, а вход —
   всегда `buy`/`sell`, которым граница (`S1-01`) пустой символ запрещает.
5. **`reason` пишется всегда, включая неторговые сделки.** Разбор — в `docs/mt5-assumptions.md`,
   допущение 10.

Чего здесь намеренно нет: чтения `open_positions.profit` — плавающий результат в `net_pnl`
не попадает никогда (`S1-03`, `OpenPositionSnapshot`); и повторной валидации — она
отработала на границе один раз (`CLAUDE.md` §5).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.errors import CODE_BY_STATUS, ApiError
from app.core.ids import uuid7
from app.core.logging import get_logger
from app.domains.accounts import models as account_models
from app.domains.accounts import service as accounts
from app.domains.ingest import models
from app.domains.ingest.normalizer import (
    DealType,
    Entry,
    NormalizedDeal,
    Reason,
    deal_role,
    normalize_batch,
    to_utc,
)
from app.domains.ingest.position_builder import (
    BuiltPosition,
    PositionBuildError,
    build_position,
    group_position_deals,
    open_position_snapshot,
    quantize_money,
    quantize_quantity,
)
from app.domains.ingest.schemas import (
    MAX_DEALS_PER_BATCH,
    IngestDealsBatch,
    IngestOpenPosition,
)
from app.domains.ingest.symbol_registry import ensure_symbols

log = get_logger(__name__)

BATCH_TOO_LARGE_CODE = CODE_BY_STATUS[413]
BATCH_TOO_LARGE_MESSAGE = f"Батч больше {MAX_DEALS_PER_BATCH} сделок"

# Тексты в `sync_runs.error`. Их видит человек на экране счёта (`S1-11`), поэтому они
# по-русски и без подробностей извне: текст исключения может нести содержимое строки.
RUN_ERROR_TOO_LARGE = f"Батч превысил предел в {MAX_DEALS_PER_BATCH} сделок и не принят"
RUN_ERROR_ARCHIVED = "Счёт в архиве: батч не принят"
RUN_ERROR_INTERNAL = "Внутренняя ошибка при обработке батча"

# Протокол Postgres кладёт число параметров оператора в int16, и asyncpg отказывает уже
# на 32768-м. Батч из 5000 сделок по 20 колонок — 100 000 параметров, то есть один
# оператор на весь батч физически невозможен. Размер куска выбран с запасом к границе,
# а не под неё: колонку сюда добавят раньше, чем вспомнят про этот расчёт.
DEAL_INSERT_CHUNK = 500
POSITION_UPSERT_CHUNK = 500
POSITION_SELECT_CHUNK = 1000

# Колонки `positions`, которые пересборка переписывает. `id` здесь нет — на нём висит
# пользовательский слой (`journal_entries`, `reflections`, `attachments`), и UPSERT обязан
# его сохранить. `is_manual` нет по той же причине: ручная сделка (`S2-03`) получает
# отрицательный `position_id` и с ингестом не пересекается, но правило дешевле проверки.
POSITION_UPDATE_COLUMNS = (
    "symbol_raw",
    "symbol_norm",
    "direction",
    "status",
    "open_time",
    "close_time",
    "volume_opened",
    "volume_closed",
    "avg_entry_price",
    "avg_exit_price",
    "gross_pnl",
    "commission",
    "swap",
    "fee",
    "net_pnl",
    "deals_count",
    "duration_seconds",
    "close_reason",
    "rebuilt_at",
)

ZERO_MONEY = quantize_money(Decimal(0))
ZERO_QUANTITY = quantize_quantity(Decimal(0))


@dataclass(frozen=True, slots=True)
class StoredDeal:
    """Строка `deals` в том объёме, который читает сборщик (`PositionDeal`).

    Своя структура, а не ORM-модель: `Deal.deal_type` типизирован как `str`, а сборщику
    нужны литералы `SPEC.md` 6.2. Заодно перечень полей остаётся закрытым — `comment`
    и `raw` сюда не попадают, и подсмотреть в них признак стопа мимо `reason` нечем.
    """

    deal_ticket: int
    position_id: int
    symbol_raw: str
    deal_type: DealType
    entry: Entry
    reason: Reason
    volume: Decimal
    price: Decimal
    profit: Decimal
    commission: Decimal
    swap: Decimal
    fee: Decimal
    time_utc: datetime


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Ответ SPEC.md 5.3, пункт 7, в терминах домена."""

    received: int
    inserted: int
    positions_rebuilt: int
    sync_run_id: int

    @property
    def duplicates(self) -> int:
        return self.received - self.inserted


def _now() -> datetime:
    return datetime.now(UTC)


def batch_too_large(received: int) -> ApiError:
    return ApiError(
        BATCH_TOO_LARGE_CODE,
        BATCH_TOO_LARGE_MESSAGE,
        status_code=413,
        details={"received": received, "limit": MAX_DEALS_PER_BATCH},
    )


def account_archived() -> ApiError:
    return ApiError(
        accounts.ACCOUNT_ARCHIVED_CODE,
        accounts.ACCOUNT_ARCHIVED_MESSAGE,
        status_code=422,
    )


async def load_account(session: AsyncSession, account_id: UUID) -> account_models.TradingAccount:
    """Счёт батча. Владельца здесь нет и не должно быть.

    Скоупинг по пользователю (`CLAUDE.md` §2) — правило пользовательского API, где счёт
    приходит из браузера с сессией. Ингест приходит по сервисному токену установки
    (SPEC.md 5.3), у него пользователя нет вовсе, и подставить сюда владельца было бы
    выдумкой. Несуществующий счёт — `404`, как и везде.
    """
    account = await session.get(account_models.TradingAccount, account_id)
    if account is None:
        raise ApiError(
            accounts.ACCOUNT_NOT_FOUND_CODE, accounts.ACCOUNT_NOT_FOUND_MESSAGE, status_code=404
        )
    return account


async def ingest_batch(
    session: AsyncSession,
    account: account_models.TradingAccount,
    batch: IngestDealsBatch,
    *,
    started_at: datetime,
) -> IngestResult:
    """Весь батч одной транзакцией: сделки, позиции, карточка счёта, строка `sync_runs`.

    Счёт на паузе батч **принимает**. Пауза — просьба не ходить к брокеру (`sync_now`
    отвечает на неё `422`), а не запрет хранить уже полученные факты; `apply_sync_result`
    сам знает, что статус паузы синк не трогает.
    """
    normalized = normalize_batch(batch)
    if normalized.unknown_codes:
        # Одна строка на батч, а не на сделку: коды сворачиваются в 'other' и батч
        # принимается целиком, исходные числа остаются в `deals.raw`.
        log.warning(
            "ingest.unknown_codes",
            account_id=str(account.id),
            codes=[
                {"field": item.field, "code": item.code, "count": item.count}
                for item in normalized.unknown_codes
            ],
        )

    inserted = await _insert_deals(session, account.id, batch.source, normalized.deals)
    affected = _affected_positions(normalized.deals, batch.open_positions)
    rebuilt = await _rebuild_positions(session, account.id, batch, affected)

    accounts.apply_sync_result(
        account,
        currency=batch.account_info.currency,
        margin_mode=batch.account_info.margin_mode,
        server_utc_offset_minutes=batch.server_utc_offset_minutes,
    )

    sync_run_id = await _record_run(
        session,
        account.id,
        batch.source,
        started_at=started_at,
        received=len(batch.deals),
        inserted=inserted,
        rebuilt=rebuilt,
        offset_minutes=batch.server_utc_offset_minutes,
        error=None,
    )
    await session.commit()
    return IngestResult(
        received=len(batch.deals),
        inserted=inserted,
        positions_rebuilt=rebuilt,
        sync_run_id=sync_run_id,
    )


async def record_failed_run(
    account_id: UUID,
    source: str,
    *,
    started_at: datetime,
    received: int,
    offset_minutes: int | None,
    error: str,
) -> None:
    """Строка `sync_runs` про отказ — **своей** транзакцией.

    Иначе отказа не видно нигде: транзакция батча откатывается целиком, и запись о ней
    откатилась бы вместе с ней. А человеку нужна именно она — историю синков показывает
    экран счёта (`S1-11`), и «последний синк был вчера» без причины неотличимо от
    «коллектор не запускался».

    Батч, не дошедший до счёта (неразобранное тело, неизвестный `account_id`), строки не
    оставляет: привязать её не к чему — `sync_runs.account_id` ссылается на реальный счёт.
    """
    async with get_session_factory()() as session:
        await _record_run(
            session,
            account_id,
            source,
            started_at=started_at,
            received=received,
            inserted=0,
            rebuilt=0,
            offset_minutes=offset_minutes,
            error=error,
        )
        await session.commit()


async def _record_run(
    session: AsyncSession,
    account_id: UUID,
    source: str,
    *,
    started_at: datetime,
    received: int,
    inserted: int,
    rebuilt: int,
    offset_minutes: int | None,
    error: str | None,
) -> int:
    statement = (
        pg_insert(models.SyncRun)
        .values(
            account_id=account_id,
            source=source,
            started_at=started_at,
            finished_at=_now(),
            deals_received=received,
            deals_new=inserted,
            positions_rebuilt=rebuilt,
            server_utc_offset_minutes=offset_minutes,
            error=error,
        )
        .returning(models.SyncRun.id)
    )
    return (await session.execute(statement)).scalar_one()


def _affected_positions(
    deals: Sequence[NormalizedDeal], open_positions: Sequence[IngestOpenPosition]
) -> set[int]:
    """`position_id`, которые батч трогает (SPEC.md 5.3, пункт 4).

    Правило ролей берётся у нормализатора: пополнение счёта позицию не трогает, даже если
    брокер проставил ему номер (§6.2).
    """
    affected = {
        deal.position_id
        for deal in deals
        if deal_role(deal.deal_type, deal.position_id) != "excluded"
    }
    affected |= {record.position_id for record in open_positions}
    return affected


async def _insert_deals(
    session: AsyncSession, account_id: UUID, source: str, deals: Sequence[NormalizedDeal]
) -> int:
    """`INSERT … ON CONFLICT DO NOTHING` (SPEC.md 5.3, пункт 2). Возвращает число новых.

    `RETURNING` при `DO NOTHING` отдаёт только реально вставленные строки, поэтому число
    здесь измеренное, а не разница множеств, посчитанная до вставки.
    """
    rows = _deal_rows(account_id, source, deals)
    inserted = 0
    for chunk in _chunks(rows, DEAL_INSERT_CHUNK):
        result = await session.execute(
            pg_insert(models.Deal)
            .values(chunk)
            .on_conflict_do_nothing(
                index_elements=[models.Deal.account_id, models.Deal.deal_ticket]
            )
            .returning(models.Deal.deal_ticket)
        )
        inserted += len(result.scalars().all())
    return inserted


def _deal_rows(
    account_id: UUID, source: str, deals: Sequence[NormalizedDeal]
) -> list[dict[str, Any]]:
    """Строки для вставки: без повторов внутри батча и в порядке тикета.

    Дедупликация нужна счётчику, а не вставке: `DO NOTHING` съел бы повтор и сам, но
    `duplicates = received − inserted` тогда считал бы повторённую внутри одного батча
    сделку новой ровно один раз, а не ноль.

    Порядок — тот же довод, что у `ensure_symbols`: многострочный INSERT берёт строчные
    замки в порядке VALUES, и два синка одного счёта, идущие в разном порядке, встают
    во взаимоблокировку.
    """
    unique: dict[int, NormalizedDeal] = {}
    for deal in deals:
        unique.setdefault(deal.deal_ticket, deal)
    return [
        {
            "account_id": account_id,
            "deal_ticket": deal.deal_ticket,
            "order_ticket": deal.order_ticket,
            "position_id": deal.position_id,
            "symbol_raw": deal.symbol_raw,
            "deal_type": deal.deal_type,
            "entry": deal.entry,
            "reason": deal.reason,
            "volume": deal.volume,
            "price": deal.price,
            "profit": deal.profit,
            "commission": deal.commission,
            "swap": deal.swap,
            "fee": deal.fee,
            "time_utc": deal.time_utc,
            "time_server": deal.time_server,
            "comment": deal.comment,
            "magic": deal.magic,
            "raw": deal.raw,
            "source": source,
        }
        for _, deal in sorted(unique.items())
    ]


async def _stored_deals(
    session: AsyncSession, account_id: UUID, position_ids: Sequence[int]
) -> list[StoredDeal]:
    """Все сделки счёта по затронутым позициям — включая приехавшие прошлыми батчами."""
    deal = models.Deal
    found: list[StoredDeal] = []
    for chunk in _chunks(list(position_ids), POSITION_SELECT_CHUNK):
        rows = await session.execute(
            select(
                deal.deal_ticket,
                deal.position_id,
                deal.symbol_raw,
                deal.deal_type,
                deal.entry,
                deal.reason,
                deal.volume,
                deal.price,
                deal.profit,
                deal.commission,
                deal.swap,
                deal.fee,
                deal.time_utc,
            ).where(deal.account_id == account_id, deal.position_id.in_(chunk))
        )
        found.extend(
            StoredDeal(
                deal_ticket=row.deal_ticket,
                position_id=row.position_id,
                symbol_raw=row.symbol_raw,
                # cast, а не проверка: словари `deal_type`/`entry`/`reason` в базу пишет
                # только этот модуль, через нормализатор. `reason` объявлен nullable, но
                # ингест пишет его всегда; даже просочившийся NULL безвреден — он доедет
                # ровно до `positions.close_reason`, которая тоже nullable.
                deal_type=cast(DealType, row.deal_type),
                entry=cast(Entry, row.entry),
                reason=cast(Reason, row.reason),
                volume=row.volume,
                price=row.price,
                profit=row.profit,
                commission=row.commission,
                swap=row.swap,
                fee=row.fee,
                time_utc=row.time_utc,
            )
            for row in rows
        )
    return found


async def _rebuild_positions(
    session: AsyncSession,
    account_id: UUID,
    batch: IngestDealsBatch,
    affected: set[int],
) -> int:
    """Пересборка затронутых позиций. Возвращает число записанных строк `positions`."""
    if not affected:
        return 0

    snapshots = {record.position_id: record for record in batch.open_positions}
    grouped = group_position_deals(await _stored_deals(session, account_id, sorted(affected)))

    built: list[BuiltPosition] = []
    # Открытые позиции, у которых в базе нет ни одной сделки (SPEC.md 5.3, пункт 5):
    # история ещё не догружена. Строка заводится из `open_positions`, а когда сделки
    # приедут, тот же UPSERT пересоберёт её по ним и сохранит `positions.id`.
    without_deals: list[IngestOpenPosition] = []
    for position_id in sorted(affected):
        group = grouped.get(position_id)
        record = snapshots.get(position_id)
        if group is None:
            if record is not None:
                without_deals.append(record)
            continue
        try:
            built.append(
                build_position(
                    group,
                    open_position=None if record is None else open_position_snapshot(record),
                )
            )
        except PositionBuildError as error:
            # Не отказ батча: сделки уже сохранены, а вход приедет следующим окном синка.
            # Текст — собственная константа сборщика, не внешний ввод.
            log.warning(
                "ingest.position_unbuildable",
                account_id=str(account_id),
                position_id=position_id,
                reason=str(error),
            )

    known = await ensure_symbols(
        session,
        [
            *(position.symbol_raw for position in built),
            *(record.symbol for record in without_deals),
        ],
    )
    rebuilt_at = _now()
    rows = [
        _built_position_row(account_id, position, known[position.symbol_raw].norm, rebuilt_at)
        for position in built
    ]
    rows.extend(
        _open_position_row(
            account_id,
            record,
            batch.server_utc_offset_minutes,
            known[record.symbol].norm,
            rebuilt_at,
        )
        for record in without_deals
    )
    if not rows:
        return 0
    rows.sort(key=lambda row: cast(int, row["position_id"]))

    for chunk in _chunks(rows, POSITION_UPSERT_CHUNK):
        statement = pg_insert(models.Position).values(chunk)
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[models.Position.account_id, models.Position.position_id],
                set_={name: statement.excluded[name] for name in POSITION_UPDATE_COLUMNS},
            )
        )
    return len(rows)


def _built_position_row(
    account_id: UUID, position: BuiltPosition, symbol_norm: str, rebuilt_at: datetime
) -> dict[str, Any]:
    return {
        # `id` проставляется явно: при многострочном INSERT питоновский default колонки
        # применяется не к каждому словарю. На конфликте он не в `set_`, поэтому
        # существующая строка свой `id` сохраняет — на нём висит пользовательский слой.
        "id": uuid7(),
        "account_id": account_id,
        "position_id": position.position_id,
        "symbol_raw": position.symbol_raw,
        "symbol_norm": symbol_norm,
        "direction": position.direction,
        "status": position.status,
        "open_time": position.open_time,
        "close_time": position.close_time,
        "volume_opened": position.volume_opened,
        "volume_closed": position.volume_closed,
        "avg_entry_price": position.avg_entry_price,
        "avg_exit_price": position.avg_exit_price,
        "gross_pnl": position.gross_pnl,
        "commission": position.commission,
        "swap": position.swap,
        "fee": position.fee,
        "net_pnl": position.net_pnl,
        "deals_count": position.deals_count,
        "duration_seconds": position.duration_seconds,
        "close_reason": position.close_reason,
        "is_manual": False,
        "rebuilt_at": rebuilt_at,
    }


def _open_position_row(
    account_id: UUID,
    record: IngestOpenPosition,
    server_utc_offset_minutes: int,
    symbol_norm: str,
    rebuilt_at: datetime,
) -> dict[str, Any]:
    """Открытая позиция, у которой сделок в базе ещё нет (SPEC.md 5.3, пункт 5).

    Деньги — нули, а не `record.profit`. Плавающий результат в `net_pnl` не попадает
    никогда: на этом стоит вся сводка `S2-05`, и сборщик (`S1-03`) поле `profit` не
    объявляет вовсе. Здесь сборщика нет, поэтому запрет держится этой строкой.
    """
    return {
        "id": uuid7(),
        "account_id": account_id,
        "position_id": record.position_id,
        "symbol_raw": record.symbol,
        "symbol_norm": symbol_norm,
        "direction": "long" if record.type == 0 else "short",
        "status": "open",
        "open_time": to_utc(record.time_server, server_utc_offset_minutes),
        "close_time": None,
        "volume_opened": quantize_quantity(record.volume),
        "volume_closed": ZERO_QUANTITY,
        "avg_entry_price": quantize_quantity(record.price_open),
        "avg_exit_price": None,
        "gross_pnl": ZERO_MONEY,
        "commission": ZERO_MONEY,
        "swap": ZERO_MONEY,
        "fee": ZERO_MONEY,
        "net_pnl": ZERO_MONEY,
        "deals_count": 0,
        "duration_seconds": None,
        "close_reason": None,
        "is_manual": False,
        "rebuilt_at": rebuilt_at,
    }


def _chunks(items: list[Any], size: int) -> Iterator[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
