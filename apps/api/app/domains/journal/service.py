"""Журнал: список позиций и карточка — SPEC.md 5.4.

Четыре правила, из которых растёт весь модуль.

1. **Скоупинг по владельцу в каждом запросе.** Позиции достаются только через счета
   пользователя. Чужой `account_id` в фильтре — `404`, а не пустой список и не `403`:
   существование чужого счёта наружу не подтверждается (`CLAUDE.md` §2).
2. **Порядок полный, а не «по полю».** Ни одно из пяти полей сортировки не уникально,
   поэтому и `ORDER BY` (`_order_by`), и предикат курсора (`_after`) строятся из пары
   `(поле, positions.id)`. Разъехавшись, они начали бы терять строки на границе страницы
   (разбор — в docstring `cursor.py`).
3. **Открытые позиции не прячутся.** У них `close_time` и `duration_seconds` пусты, и
   сортировка по этим полям ставит их первой группой в обе стороны (`NULLS FIRST` в
   `_order_by`), а фильтр периода сравнивает их по времени открытия. Позиция, которую человек держит
   прямо сейчас, — последнее, что журнал имеет право спрятать на пятой странице.
4. **Запросов на страницу — фиксированное число, не по строке на позицию.** Запись
   журнала и рефлексия приходят внешними соединениями (обе 1:1 к позиции), вложения —
   одним запросом на всю страницу.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, UnaryExpression, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.errors import ApiError
from app.domains.accounts import models as account_models
from app.domains.accounts import service as accounts_service
from app.domains.ingest import models as ingest_models
from app.domains.journal import models
from app.domains.journal.cursor import Cursor, Sort, encode_cursor
from app.domains.journal.schemas import PositionsQuery

POSITION_NOT_FOUND_CODE = "position_not_found"
POSITION_NOT_FOUND_MESSAGE = "Позиция не найдена"

STATUS_CLOSED = "closed"

# Символы `LIKE`, которые в строке поиска означают себя, а не шаблон: без экранирования
# `%` от пользователя превращает поиск в «показать всё».
LIKE_ESCAPE = "\\"
LIKE_WILDCARDS = ("%", "_")

SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "close_time": ingest_models.Position.close_time,
    "open_time": ingest_models.Position.open_time,
    "net_pnl": ingest_models.Position.net_pnl,
    "symbol_norm": ingest_models.Position.symbol_norm,
    "duration_seconds": ingest_models.Position.duration_seconds,
}


class RowValues:
    """Разобранная строка выдачи: SQLAlchemy отдаёт кортеж, читать его по индексам больно."""

    __slots__ = ("account", "entry", "position", "reflection")

    def __init__(
        self,
        position: ingest_models.Position,
        account: account_models.TradingAccount,
        entry: models.JournalEntry | None,
        reflection: models.Reflection | None,
    ) -> None:
        self.position = position
        self.account = account
        self.entry = entry
        self.reflection = reflection


def position_not_found() -> ApiError:
    return ApiError(POSITION_NOT_FOUND_CODE, POSITION_NOT_FOUND_MESSAGE, status_code=404)


def _escape_like(value: str) -> str:
    escaped = value.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
    for wildcard in LIKE_WILDCARDS:
        escaped = escaped.replace(wildcard, LIKE_ESCAPE + wildcard)
    return escaped


async def resolve_account_ids(
    session: AsyncSession, user_id: UUID, requested: Sequence[UUID]
) -> list[UUID]:
    """Счета, по которым разрешено смотреть журнал.

    Пустой фильтр — все неархивированные счета пользователя (SPEC.md 5.1). Явный список
    архив не отсекает: сделки архивного счёта остаются (SPEC.md 5.2), и попросивший его
    прямо должен их увидеть.

    Чужой или несуществующий идентификатор роняет **весь** запрос в `404`, а не выпадает
    из выборки молча. Отдать «своё из списка» значило бы вернуть не тот список, который
    просили, и человек считал бы неполную выборку полной. В `details` возвращаются те же
    строки, что прислал клиент, — он их и так знает, а фронту (S2-06) по ним видно, какой
    счёт выбросить из сохранённого выбора.
    """
    if not requested:
        statement = select(account_models.TradingAccount.id).where(
            account_models.TradingAccount.user_id == user_id,
            account_models.TradingAccount.status != accounts_service.STATUS_ARCHIVED,
        )
        return list((await session.execute(statement)).scalars().all())

    unique = list(dict.fromkeys(requested))
    statement = select(account_models.TradingAccount.id).where(
        account_models.TradingAccount.user_id == user_id,
        account_models.TradingAccount.id.in_(unique),
    )
    owned = set((await session.execute(statement)).scalars().all())
    missing = [str(account_id) for account_id in unique if account_id not in owned]
    if missing:
        raise ApiError(
            accounts_service.ACCOUNT_NOT_FOUND_CODE,
            accounts_service.ACCOUNT_NOT_FOUND_MESSAGE,
            status_code=404,
            details={"account_ids": missing},
        )
    return unique


def _event_time() -> ColumnElement[Any]:
    """Время, по которому фильтруется период: закрытие, а у открытой позиции — открытие.

    Иначе фильтр по датам выбрасывал бы из журнала все открытые позиции разом: у них
    `close_time` пуст, и любое сравнение с ним ложно.
    """
    return func.coalesce(ingest_models.Position.close_time, ingest_models.Position.open_time)


def _filters(query: PositionsQuery, account_ids: Sequence[UUID]) -> list[ColumnElement[bool]]:
    position = ingest_models.Position
    clauses: list[ColumnElement[bool]] = [position.account_id.in_(list(account_ids))]

    if query.status is not None:
        clauses.append(position.status == query.status)
    if query.date_from is not None:
        clauses.append(_event_time() >= query.date_from)
    if query.date_to is not None:
        # Полуинтервал: с включённой правой границей «до 1 октября» либо теряет сделки
        # последней секунды, либо тянет за собой день октября — в зависимости от того,
        # что фронт подставит во время.
        clauses.append(_event_time() < query.date_to)
    if query.symbol is not None:
        clauses.append(position.symbol_norm == query.symbol)
    if query.direction is not None:
        clauses.append(position.direction == query.direction)
    if query.result is not None:
        clauses.append(_result_clause(query.result))
    if query.has_reflection is not None:
        filled = models.Reflection.filled_at
        clauses.append(filled.isnot(None) if query.has_reflection else filled.is_(None))

    tags = query.tag_list
    if tags:
        # `@>`: позиция должна нести все перечисленные теги. Второй тег сужает выборку,
        # а не расширяет её, — иначе фильтр вёл бы себя обратно ожиданию.
        clauses.append(models.JournalEntry.tags.contains(tags))

    if query.q is not None:
        pattern = f"%{_escape_like(query.q)}%"
        clauses.append(
            or_(
                position.symbol_norm.ilike(pattern, escape=LIKE_ESCAPE),
                position.symbol_raw.ilike(pattern, escape=LIKE_ESCAPE),
                models.JournalEntry.notes.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    return clauses


def _result_clause(result: str) -> ColumnElement[bool]:
    """SPEC.md 5.4: `> 0` win, `< 0` loss, `= 0` breakeven — и только у закрытых.

    Точный ноль, без полосы вокруг него: спека называет границу прямо. Цена решения
    честная и её надо знать — на реальном счёте комиссия сдвигает `net_pnl` с нуля почти
    всегда, поэтому `be` будет почти пустым.
    """
    position = ingest_models.Position
    closed = position.status == STATUS_CLOSED
    if result == "win":
        return and_(closed, position.net_pnl > 0)
    if result == "loss":
        return and_(closed, position.net_pnl < 0)
    return and_(closed, position.net_pnl == 0)


def _order_by(sort: Sort) -> list[UnaryExpression[Any]]:
    """Полный порядок: поле сортировки, затем `positions.id`.

    Второй ключ — не украшение. Ни одно из пяти полей SPEC.md 5.4 не уникально, и без
    `id` строки с одинаковым значением идут в порядке, который Postgres не обещает: он
    меняется от плана к плану. Курсор при этом указывает ровно в такую строку.

    `NULLS FIRST` ставится только там, где пусто бывает: у `close_time` и
    `duration_seconds` (правило 3 в шапке модуля). На остальных трёх колонках `not null`,
    и лишний `NULLS FIRST` там только мешал бы планировщику взять индекс.
    """
    column = SORT_COLUMNS[sort.field]
    identifier = ingest_models.Position.id
    if sort.descending:
        primary = column.desc()
        return [primary.nulls_first() if sort.nullable else primary, identifier.desc()]
    primary = column.asc()
    return [primary.nulls_first() if sort.nullable else primary, identifier.asc()]


def _after(sort: Sort, cursor: Cursor) -> ColumnElement[bool]:
    """«Строго после курсора» в том же порядке, что задаёт `_order_by`.

    Пара `(значение, id)` сравнивается развёрнуто — `поле < v OR (поле = v AND id < pid)`,
    — а не строчным сравнением `(поле, id) < (v, pid)`: результат тот же, но типы
    параметров выводятся из колонок по одному, без опоры на то, как asyncpg и Postgres
    выведут их внутри конструктора строки.

    Ветка `cursor.value is None` — не «значения нет», а «курсор внутри группы открытых
    позиций». Группа идёт первой, поэтому после такой строки лежит остаток группы
    (по `id` в ту же сторону) и весь непустой хвост целиком.
    """
    column = SORT_COLUMNS[sort.field]
    identifier = ingest_models.Position.id

    if cursor.value is None:
        within_nulls = and_(
            column.is_(None),
            identifier < cursor.position_id if sort.descending else identifier > cursor.position_id,
        )
        return or_(within_nulls, column.isnot(None))

    if sort.descending:
        beyond = or_(
            column < cursor.value,
            and_(column == cursor.value, identifier < cursor.position_id),
        )
    else:
        beyond = or_(
            column > cursor.value,
            and_(column == cursor.value, identifier > cursor.position_id),
        )
    # `isnot(None)` не для красоты: строки без значения уже позади, а сравнение с NULL
    # даёт NULL, то есть «не знаю» вместо «не подходит».
    return and_(column.isnot(None), beyond)


def _base_statement(query: PositionsQuery, account_ids: Sequence[UUID]) -> Select[Any]:
    """Позиция, её счёт и пользовательский слой — одним запросом.

    `journal_entries` и `reflections` висят на `positions.id` первичным ключом, то есть
    строго 1:1: внешнее соединение с ними не размножает строки и не портит ни `LIMIT`,
    ни курсор. С `attachments` так нельзя — их много на позицию, поэтому они считаются
    отдельно (`attachment_counts`).
    """
    return (
        select(
            ingest_models.Position,
            account_models.TradingAccount,
            models.JournalEntry,
            models.Reflection,
        )
        .join(
            account_models.TradingAccount,
            account_models.TradingAccount.id == ingest_models.Position.account_id,
        )
        .outerjoin(
            models.JournalEntry, models.JournalEntry.position_id == ingest_models.Position.id
        )
        .outerjoin(models.Reflection, models.Reflection.position_id == ingest_models.Position.id)
        .where(*_filters(query, account_ids))
    )


async def list_positions(
    session: AsyncSession, user_id: UUID, query: PositionsQuery
) -> tuple[list[RowValues], dict[UUID, int], str | None]:
    """Страница журнала: строки, счётчики вложений и курсор следующей страницы."""
    account_ids = await resolve_account_ids(session, user_id, query.account_id_list)
    sort = query.sort_key
    after = query.cursor_key

    statement = _base_statement(query, account_ids)
    if after is not None:
        statement = statement.where(_after(sort, after))
    # На одну строку больше страницы: наличие следующей страницы узнаётся так, а не
    # отдельным `count(*)` по всему журналу.
    statement = statement.order_by(*_order_by(sort)).limit(query.limit + 1)

    fetched = [RowValues(*row) for row in (await session.execute(statement)).all()]
    has_more = len(fetched) > query.limit
    rows = fetched[: query.limit]

    next_cursor: str | None = None
    if has_more and rows:
        last = rows[-1].position
        next_cursor = encode_cursor(sort, getattr(last, sort.field), last.id)
    counts = await attachment_counts(session, [row.position.id for row in rows])
    return rows, counts, next_cursor


async def attachment_counts(session: AsyncSession, position_ids: Sequence[UUID]) -> dict[UUID, int]:
    """Вложения страницы — одним запросом, не по запросу на строку.

    Таблица пуста до `S2-04`, и на пустой таблице разница незаметна. Заметной она станет
    ровно тогда, когда вложения появятся, а переписывать список к тому моменту будет уже
    некому — счётчик по строке на этом экране это N+1 на каждый скролл.
    """
    if not position_ids:
        return {}
    statement = (
        select(models.Attachment.position_id, func.count())
        .where(models.Attachment.position_id.in_(list(position_ids)))
        .group_by(models.Attachment.position_id)
    )
    return {row[0]: row[1] for row in (await session.execute(statement)).all()}


async def get_position(session: AsyncSession, user_id: UUID, position_id: UUID) -> RowValues:
    """Позиция пользователя. Чужая и несуществующая неотличимы: обе — 404.

    Архив здесь не фильтруется: сделки архивного счёта остаются, и открытая по ссылке
    карточка обязана открыться.
    """
    statement = (
        select(
            ingest_models.Position,
            account_models.TradingAccount,
            models.JournalEntry,
            models.Reflection,
        )
        .join(
            account_models.TradingAccount,
            account_models.TradingAccount.id == ingest_models.Position.account_id,
        )
        .outerjoin(
            models.JournalEntry, models.JournalEntry.position_id == ingest_models.Position.id
        )
        .outerjoin(models.Reflection, models.Reflection.position_id == ingest_models.Position.id)
        .where(
            ingest_models.Position.id == position_id,
            account_models.TradingAccount.user_id == user_id,
        )
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise position_not_found()
    return RowValues(*row)


async def position_deals(
    session: AsyncSession, position: ingest_models.Position
) -> list[ingest_models.Deal]:
    """Сделки позиции в хронологическом порядке.

    Связь идёт по паре `(account_id, position_id)` — это индекс `ix_deals_account_id_
    position_id` и это же ключ, по которому позиция собиралась. `deal_ticket` вторым
    ключом: у двух сделок одной позиции легко совпадает секунда, и без него порядок
    сделок в карточке менялся бы от запроса к запросу.
    """
    statement = (
        select(ingest_models.Deal)
        .where(
            ingest_models.Deal.account_id == position.account_id,
            ingest_models.Deal.position_id == position.position_id,
        )
        .order_by(ingest_models.Deal.time_utc, ingest_models.Deal.deal_ticket)
    )
    return list((await session.execute(statement)).scalars().all())
