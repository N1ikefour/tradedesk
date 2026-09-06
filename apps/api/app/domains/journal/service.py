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

Вторая половина модуля — запись (S2-02): `save_entry`, `save_reflection` и словарь тегов.
Правило 1 действует и там: любой маршрут записи начинается с `ensure_owned_position`, и
чужая позиция даёт тот же `404`, что и на чтении. Про `filled_at` и про то, какое
написание тега побеждает, — в docstring соответствующих функций.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    CursorResult,
    Select,
    UnaryExpression,
    and_,
    func,
    null,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.errors import ApiError
from app.core.ids import uuid7
from app.domains.accounts import models as account_models
from app.domains.accounts import service as accounts_service
from app.domains.ingest import models as ingest_models
from app.domains.journal import models, schemas
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


# --- запись: entry, reflection, словарь тегов (S2-02) --------------------------

TAG_NOT_FOUND_CODE = "tag_not_found"
TAG_NOT_FOUND_MESSAGE = "Тег не найден"

# Ключ транзакционной advisory-блокировки словаря тегов. Нужна потому, что уникальность
# тегов без учёта регистра держится **кодом**, а не индексом: в схеме S0-03 стоит
# `unique (user_id, name)`, то есть `Trend` и `trend` для Postgres разные строки. Два
# одновременных сохранения карточки с разным написанием нового тега завели бы обе.
# Блокировка одна на пользователя, а не по тегу: с блокировкой на тег два запроса с
# пересекающимися наборами могли бы взять их в разном порядке и встать намертво.
#
# Держится она до конца транзакции запроса, а берётся в `resolve_tags` — то есть до записи
# самих `journal_entries`. Поэтому закрыта не только «две вставки одного тега», но и
# «переименование посреди сохранения карточки»: `upsert_tag` и `delete_tag` берут тот же
# ключ, и массовый `UPDATE` тегов не может встать между чтением словаря и записью строки
# журнала. Второе следует из механики, а не из теста: под тестом стоит первое —
# `test_the_tag_dictionary_lock_keeps_two_saves_out_of_the_window` меряет пик
# одновременности в окне между чтением словаря и вставкой тега и требует единицы.
#
# ⚠️ Настоящее место этому правилу — уникальный индекс по `(user_id, lower(name))` (X-35);
# он требует миграции, которой в этой задаче нет. Блокировка закрывает гонку, но не
# защищает от строк, заведённых мимо этого кода.
_TAG_LOCK_NAMESPACE = "journal_tags"


def tag_not_found() -> ApiError:
    return ApiError(TAG_NOT_FOUND_CODE, TAG_NOT_FOUND_MESSAGE, status_code=404)


def _now() -> datetime:
    return datetime.now(UTC)


async def ensure_owned_position(session: AsyncSession, user_id: UUID, position_id: UUID) -> None:
    """Позиция принадлежит пользователю — иначе `404`, как и на чтении.

    Берётся только `positions.id`, без пользовательского слоя: строки `journal_entries` и
    `reflections` этот запрос всё равно перезапишет, а загруженные в сессию ORM-копии
    разошлись бы с тем, что вернёт `RETURNING` после UPSERT.

    Архив счёта здесь не проверяется намеренно: карточка архивного счёта открывается
    (S2-01), и запретить дописать к ней заметку значило бы показать поле, которое молча
    не сохраняется.
    """
    statement = (
        select(ingest_models.Position.id)
        .join(
            account_models.TradingAccount,
            account_models.TradingAccount.id == ingest_models.Position.account_id,
        )
        .where(
            ingest_models.Position.id == position_id,
            account_models.TradingAccount.user_id == user_id,
        )
    )
    if (await session.execute(statement)).scalar_one_or_none() is None:
        raise position_not_found()


async def _lock_tag_dictionary(session: AsyncSession, user_id: UUID) -> None:
    """Блокировка держится до конца транзакции запроса — см. `_TAG_LOCK_NAMESPACE`."""
    key = f"{_TAG_LOCK_NAMESPACE}:{user_id}"
    await session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))


async def _dictionary(session: AsyncSession, user_id: UUID) -> dict[str, models.Tag]:
    """Словарь тегов пользователя по ключу сравнения без учёта регистра.

    Читается целиком и сводится в Python, а не сравнивается `lower()` в SQL: правило
    складывания регистров должно быть одно на всю систему, а `lower()` Postgres и
    `casefold()` Python совпадают не везде. Словарь одного человека — десятки строк.
    """
    statement = select(models.Tag).where(models.Tag.user_id == user_id).order_by(models.Tag.name)
    found: dict[str, models.Tag] = {}
    for tag in (await session.execute(statement)).scalars():
        # Дубль по регистру возможен только у строк, заведённых мимо этого кода
        # (см. `_TAG_LOCK_NAMESPACE`). `order_by` здесь ради него: без порядка выбор между
        # двумя такими строками менялся бы от запроса к запросу, а с ним — 500 на
        # `scalar_one` не случается вовсе, и написание остаётся одним и тем же.
        found.setdefault(schemas.fold_tag(tag.name), tag)
    return found


async def resolve_tags(session: AsyncSession, user_id: UUID, names: Sequence[str]) -> list[str]:
    """Написания тегов, которые уйдут в `journal_entries.tags`, и заведение недостающих.

    Три решения, и все три человек видит.

    1. **Тега, которого нет в словаре, достаточно назвать.** Он заводится сам, без цвета.
       Отвергать значило бы заставить карточку сначала звать `POST /journal/tags`, то есть
       ломать автосохранение на втором запросе; а сохранить мимо словаря — получить тег,
       которого нет ни в подсказках, ни в фильтре, ни в удалении.
    2. **Написание берёт словарь, а не последний ввод.** `trend` при заведённом `Trend`
       сохранится как `Trend`. Обратное правило означало бы, что одна опечатка с CapsLock
       переименовывает тег на всех прошлых позициях разом.
    3. **Поменять написание можно ровно одним способом** — `POST /journal/tags` с новым
       написанием: это явное действие над словарём, а не побочный эффект сохранения
       заметки. Оно же переписывает тег на всех позициях (`upsert_tag`).
    """
    if not names:
        return []
    await _lock_tag_dictionary(session, user_id)
    known = await _dictionary(session, user_id)
    canonical: list[str] = []
    created: list[models.Tag] = []
    for name in names:
        key = schemas.fold_tag(name)
        existing = known.get(key)
        if existing is not None:
            canonical.append(existing.name)
            continue
        fresh = models.Tag(id=uuid7(), user_id=user_id, name=name, color=None)
        known[key] = fresh
        created.append(fresh)
        canonical.append(name)
    if created:
        session.add_all(created)
        await session.flush()
    return canonical


def _owned_positions(user_id: UUID) -> Select[Any]:
    """Идентификаторы позиций пользователя — подзапрос для массовых правок тегов.

    В `_rewrite_tag_in_entries` это **единственное**, что отделяет свои строки от чужих, а
    сам он — единственное место домена, где запрос правит строки пачкой. Поэтому скоуп
    держится тестом, а не только чтением: пара `..._leaves_the_same_tag_of_another_user_alone`
    краснеет, если условие по `user_id` отсюда убрать. Второй потребитель — `tag_usage`.
    """
    return (
        select(ingest_models.Position.id)
        .join(
            account_models.TradingAccount,
            account_models.TradingAccount.id == ingest_models.Position.account_id,
        )
        .where(account_models.TradingAccount.user_id == user_id)
    )


async def _rewrite_tag_in_entries(
    session: AsyncSession, user_id: UUID, old: str, new: str | None
) -> int:
    """Переписывает или снимает тег на всех позициях пользователя. Возвращает их число.

    `updated_at` двигается: содержимое записи журнала действительно изменилось, и
    оставить прежнюю отметку значило бы соврать всякому, кто по ней сверяется.

    Сами заметки, рефлексии и вложения не трогаются — правится ровно колонка `tags`
    (`CLAUDE.md` §2: пользовательский слой не затирается целиком ради одной колонки).
    """
    tags = models.JournalEntry.tags
    changed = func.array_remove(tags, old) if new is None else func.array_replace(tags, old, new)
    statement = (
        update(models.JournalEntry)
        .where(
            models.JournalEntry.position_id.in_(_owned_positions(user_id)),
            tags.contains([old]),
        )
        .values(tags=changed, updated_at=_now())
    )
    result = await session.execute(statement)
    # UPDATE всегда возвращает CursorResult, но типы SQLAlchemy обещают только Result.
    return cast(CursorResult[Any], result).rowcount


def _usage_counts(user_id: UUID) -> Select[Any]:
    """Сколько позиций несёт каждый тег. `unnest` в подзапросе, а не в группировке:
    Postgres вычисляет генераторы строк после агрегации, и `group by unnest(...)` не
    выполняется вовсе."""
    expanded = (
        select(func.unnest(models.JournalEntry.tags).label("name"))
        .select_from(models.JournalEntry)
        .join(
            ingest_models.Position,
            ingest_models.Position.id == models.JournalEntry.position_id,
        )
        .join(
            account_models.TradingAccount,
            account_models.TradingAccount.id == ingest_models.Position.account_id,
        )
        .where(account_models.TradingAccount.user_id == user_id)
        .subquery()
    )
    return select(expanded.c.name, func.count().label("uses")).group_by(expanded.c.name)


async def list_tags(session: AsyncSession, user_id: UUID) -> list[tuple[models.Tag, int]]:
    """Словарь тегов пользователя со счётчиком употреблений.

    Счётчик нужен не для украшения списка: удаление тега снимает его со всех позиций, и
    без числа интерфейсу нечего показать в подтверждении — человек соглашался бы вслепую.

    Порядок — по написанию без учёта регистра: `Trend` и `trend` в списке не разъезжаются
    (второе, впрочем, может появиться только мимо этого кода, см. `_TAG_LOCK_NAMESPACE`).
    """
    usage = _usage_counts(user_id).subquery()
    statement = (
        select(models.Tag, func.coalesce(usage.c.uses, 0))
        .outerjoin(usage, usage.c.name == models.Tag.name)
        .where(models.Tag.user_id == user_id)
        .order_by(func.lower(models.Tag.name), models.Tag.name)
    )
    return [(tag, count) for tag, count in (await session.execute(statement)).all()]


async def tag_usage(session: AsyncSession, user_id: UUID, name: str) -> int:
    statement = select(func.count()).select_from(
        select(models.JournalEntry.position_id)
        .where(
            models.JournalEntry.position_id.in_(_owned_positions(user_id)),
            models.JournalEntry.tags.contains([name]),
        )
        .subquery()
    )
    return (await session.execute(statement)).scalar_one()


async def upsert_tag(
    session: AsyncSession, user_id: UUID, name: str, color: str | None
) -> tuple[models.Tag, int]:
    """Заводит тег или задаёт существующему написание и цвет.

    `POST`, который не только создаёт, — намеренно. Это **единственное** место, где
    написание тега меняется: `PUT entry` его только использует (`resolve_tags`), а
    переименования у словаря по SPEC.md 5.4 нет вовсе. Без этого исправить регистр
    можно было бы только удалением, то есть потеряв тег на всех позициях.

    Смена написания переносится на позиции: в `journal_entries.tags` лежат написания из
    словаря, и оставить их старыми значило бы развести словарь с чипами в таблице.
    """
    await _lock_tag_dictionary(session, user_id)
    known = await _dictionary(session, user_id)
    existing = known.get(schemas.fold_tag(name))
    if existing is None:
        created = models.Tag(id=uuid7(), user_id=user_id, name=name, color=color)
        session.add(created)
        await session.commit()
        return created, 0

    renamed_from = existing.name
    existing.name = name
    existing.color = color
    usage = (
        await _rewrite_tag_in_entries(session, user_id, renamed_from, name)
        if renamed_from != name
        else await tag_usage(session, user_id, name)
    )
    await session.commit()
    return existing, usage


async def delete_tag(session: AsyncSession, user_id: UUID, tag_id: UUID) -> tuple[str, int]:
    """Удаляет тег из словаря и снимает его со всех позиций пользователя.

    Второе — не побочный эффект, а единственный непротиворечивый вариант. Оставить тег на
    позициях значило бы получить чип, которого нет ни в подсказках, ни в списке словаря, —
    и который вернётся в словарь сам при первом же сохранении такой карточки
    (`resolve_tags` заводит незнакомое). Удаление, которое отменяется автосохранением, —
    хуже, чем удаление, которое видно.

    Сколько позиций затронуто, возвращается наружу: спросить об этом заранее клиент может
    по `usage_count` из `GET /journal/tags`, а подтвердить факт — только этим числом.
    """
    await _lock_tag_dictionary(session, user_id)
    statement = select(models.Tag).where(models.Tag.id == tag_id, models.Tag.user_id == user_id)
    tag = (await session.execute(statement)).scalar_one_or_none()
    if tag is None:
        raise tag_not_found()
    name = tag.name
    updated = await _rewrite_tag_in_entries(session, user_id, name, None)
    await session.delete(tag)
    await session.commit()
    return name, updated


async def save_entry(
    session: AsyncSession,
    user_id: UUID,
    position_id: UUID,
    payload: schemas.JournalEntryUpdate,
) -> models.JournalEntry:
    """Полная замена записи журнала. Строка заводится первым же сохранением."""
    await ensure_owned_position(session, user_id, position_id)
    tags = await resolve_tags(session, user_id, payload.tags)
    values: dict[str, Any] = {
        "notes": payload.notes,
        "tags": tags,
        "planned_entry": payload.planned_entry,
        "planned_sl": payload.planned_sl,
        "planned_tp": payload.planned_tp,
        "risk_amount": payload.risk_amount,
        "updated_at": _now(),
    }
    statement = (
        pg_insert(models.JournalEntry)
        .values(position_id=position_id, **values)
        .on_conflict_do_update(index_elements=[models.JournalEntry.position_id], set_=values)
        .returning(models.JournalEntry)
    )
    entry = (await session.execute(statement)).scalar_one()
    await session.commit()
    return entry


async def save_reflection(
    session: AsyncSession,
    user_id: UUID,
    position_id: UUID,
    payload: schemas.ReflectionUpdate,
) -> models.Reflection:
    """Полная замена рефлексии. Всё содержательное решение — в `filled_at`.

    SPEC.md 5.4: отметка ставится «при первом сохранении с хотя бы одним заполненным
    полем». Отсюда ровно три перехода, и все три считаются на стороне Postgres — одним
    выражением в `DO UPDATE`, а не чтением с последующей записью: два автосохранения
    подряд иначе могли бы разъехаться и переставить время.

    * пусто → заполнено: `filled_at = сейчас`;
    * заполнено → заполнено: `filled_at` не двигается (`coalesce` со старым значением),
      сколько бы правок ни было. Это дата, когда человек разобрал сделку, а не дата
      последней запятой; «когда трогали» показывает `updated_at`;
    * заполнено → пусто: `filled_at` снимается. Иначе фильтр `has_reflection=true` из
      S2-01 возвращал бы позицию с пустой рефлексией, а иконка в таблице обещала бы
      разбор, которого больше нет.

    Что считается заполненным — `ReflectionUpdate.is_filled`, там же и почему.
    """
    await ensure_owned_position(session, user_id, position_id)
    now = _now()
    filled = payload.is_filled
    values: dict[str, Any] = {
        "setup_grade": payload.setup_grade,
        "execution_grade": payload.execution_grade,
        "followed_plan": payload.followed_plan,
        "emotion_before": payload.emotion_before,
        "emotion_during": payload.emotion_during,
        "emotion_after": payload.emotion_after,
        "mistakes": list(payload.mistakes),
        "confidence": payload.confidence,
        "free_text": payload.free_text,
        "updated_at": now,
    }
    # Без квалификации колонка в `set_` означает существующую строку, а не вставляемую:
    # `coalesce` здесь читает `filled_at`, который уже лежит в базе.
    kept = func.coalesce(models.Reflection.__table__.c.filled_at, now)
    statement = (
        pg_insert(models.Reflection)
        .values(position_id=position_id, filled_at=now if filled else None, **values)
        .on_conflict_do_update(
            index_elements=[models.Reflection.position_id],
            set_={**values, "filled_at": kept if filled else null()},
        )
        .returning(models.Reflection)
    )
    reflection = (await session.execute(statement)).scalar_one()
    await session.commit()
    return reflection
