"""Тела запросов и ответов журнала — SPEC.md 5.4.

Модели ответа собираются полем за полем в `from_*`, а не `model_validate` поверх
ORM-объекта, по той же причине, что и в домене счетов: список полей ответа должен быть
явным текстом, который видно в диффе. Здесь это важнее, чем кажется, — в `deals` лежит
колонка `raw` с полным ответом терминала, и `model_validate` вынес бы её наружу целиком
первым же добавлением поля в модель.

Деньги, цены и объёмы уходят строками (`core.schemas.Money`, `Quantity`): в JSON нет
десятичного типа, и число здесь означало бы double на фронте (`CLAUDE.md` §2 — никакого
float в денежных расчётах).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.core.schemas import Money, Quantity, UtcDatetime
from app.core.text import sanitize_external_text
from app.domains.accounts import models as account_models
from app.domains.ingest import models as ingest_models
from app.domains.journal import models
from app.domains.journal.cursor import (
    DEFAULT_SORT,
    INVALID_CURSOR_MESSAGE,
    SORT_ERROR,
    Cursor,
    InvalidCursorError,
    Sort,
    decode_cursor,
    parse_sort,
)

PositionStatus = Literal["open", "closed"]
PositionDirection = Literal["long", "short"]
# SPEC.md 5.4: «result считается по net_pnl: > 0 win, < 0 loss, = 0 breakeven».
PositionResult = Literal["win", "loss", "be"]
Grade = Literal["A", "B", "C", "D"]

DEFAULT_LIMIT = 50
MAX_LIMIT = 200

# Не показ, а размер ответа: без предела страница из 50 строк тащит в таблицу журнала все
# заметки целиком, а это мегабайты текста ради одной строки под символом.
NOTES_PREVIEW_LENGTH = 160
ELLIPSIS = "…"

MAX_SEARCH_LENGTH = 100
MAX_TAGS = 20
MAX_TAG_LENGTH = 64
MAX_SYMBOL_LENGTH = 32
MAX_ACCOUNT_IDS = 100

FILTER_SEPARATOR = ","

NAIVE_DATETIME_ERROR = (
    "Укажите время с часовым поясом, например 2026-09-01T00:00:00Z: "
    "без него непонятно, чей это день"
)
RANGE_ERROR = "Начало периода должно быть раньше конца"
ACCOUNT_IDS_ERROR = "account_ids — список UUID через запятую"
TOO_MANY_ACCOUNT_IDS_ERROR = f"Не больше {MAX_ACCOUNT_IDS} счетов в фильтре"
TOO_MANY_TAGS_ERROR = f"Не больше {MAX_TAGS} тегов в фильтре"
TAG_TOO_LONG_ERROR = f"Тег не длиннее {MAX_TAG_LENGTH} символов"
SYMBOL_TOO_LONG_ERROR = f"Символ не длиннее {MAX_SYMBOL_LENGTH} символов"
SEARCH_TOO_LONG_ERROR = f"Строка поиска не длиннее {MAX_SEARCH_LENGTH} символов"

_WHITESPACE_RE = re.compile(r"\s+")


def notes_preview(notes: str | None) -> str | None:
    """Одна строка заметки для таблицы. Полный текст — только в карточке."""
    if notes is None:
        return None
    collapsed = _WHITESPACE_RE.sub(" ", notes).strip()
    if not collapsed:
        return None
    if len(collapsed) <= NOTES_PREVIEW_LENGTH:
        return collapsed
    return collapsed[: NOTES_PREVIEW_LENGTH - len(ELLIPSIS)].rstrip() + ELLIPSIS


def position_result(position: ingest_models.Position) -> PositionResult | None:
    """Итог позиции по `net_pnl` — SPEC.md 5.4.

    `None` у открытой позиции, и это не пропуск. У незакрытой сделки итога ещё нет, а
    `net_pnl` на ней успел набрать комиссию и своп — то есть почти всегда отрицателен.
    Считать по нему `loss` значило бы красить живую сделку в убыток за то, что брокер
    взял комиссию на входе.
    """
    if position.status != "closed":
        return None
    if position.net_pnl > 0:
        return "win"
    if position.net_pnl < 0:
        return "loss"
    return "be"


def _split(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [part.strip() for part in raw.split(FILTER_SEPARATOR) if part.strip()]


class PositionsQuery(BaseModel):
    """Фильтры `GET /journal/positions` — SPEC.md 5.4.

    `extra="forbid"` намеренно: опечатка в имени параметра (`symbols` вместо `symbol`)
    иначе молча вернула бы нефильтрованный список, и человек принял бы чужие строки за
    свои. Лучше 400.
    """

    model_config = ConfigDict(extra="forbid")

    account_ids: str | None = Field(
        default=None,
        description="UUID счетов через запятую. Пусто — все неархивированные счета",
    )
    status: PositionStatus | None = Field(default=None)
    date_from: datetime | None = Field(
        default=None,
        alias="from",
        description=(
            "Начало периода включительно. Сравнивается с временем закрытия, "
            "а у ещё открытых позиций — с временем открытия"
        ),
    )
    date_to: datetime | None = Field(
        default=None,
        alias="to",
        description="Конец периода, не включая границу",
    )
    symbol: str | None = Field(default=None, description="Точное совпадение с symbol_norm")
    direction: PositionDirection | None = Field(default=None)
    result: PositionResult | None = Field(
        default=None, description="Только закрытые позиции: у открытых итога нет"
    )
    tags: str | None = Field(
        default=None, description="Теги через запятую. Позиция должна нести их все"
    )
    has_reflection: bool | None = Field(
        default=None, description="Заполнена ли рефлексия (`filled_at` не пуст)"
    )
    q: str | None = Field(default=None, description="Поиск по символу и тексту заметки")
    sort: str = Field(default=DEFAULT_SORT, description=SORT_ERROR)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
    cursor: str | None = Field(default=None, description="Курсор следующей страницы")

    @field_validator("date_from", "date_to")
    @classmethod
    def _requires_offset(cls, value: datetime | None) -> datetime | None:
        """Наивное время — не «UTC по умолчанию», а незаданный вопрос.

        Приняв его молча, мы сдвинули бы границу периода на смещение пользователя и
        выкинули из выборки сделки его вечера.
        """
        if value is not None and value.tzinfo is None:
            raise PydanticCustomError("naive_datetime", NAIVE_DATETIME_ERROR)
        return value

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        symbol = value.strip()
        if not symbol:
            return None
        if len(symbol) > MAX_SYMBOL_LENGTH:
            raise PydanticCustomError("symbol", SYMBOL_TOO_LONG_ERROR)
        # S1-07 кладёт в `symbol_norm` верхний регистр — сравнение идёт по колонке,
        # а не по `upper(колонка)`, иначе индекс по символу перестаёт работать.
        return symbol.upper()

    @field_validator("q")
    @classmethod
    def _search(cls, value: str | None) -> str | None:
        if value is None:
            return None
        search = value.strip()
        if not search:
            return None
        if len(search) > MAX_SEARCH_LENGTH:
            raise PydanticCustomError("q", SEARCH_TOO_LONG_ERROR)
        return search

    @field_validator("sort")
    @classmethod
    def _sort(cls, value: str) -> str:
        try:
            parse_sort(value)
        except ValueError as error:
            raise PydanticCustomError("sort", SORT_ERROR) from error
        return value

    @field_validator("cursor")
    @classmethod
    def _cursor(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Курсор разбирается здесь, а не в сервисе, — тогда он ошибка параметра запроса.

        Разбор зависит от `sort`: курсор помнит, под какой порядок собран, и под другим
        порядком означает не ту строку. Поле объявлено выше `cursor`, поэтому к моменту
        этой проверки уже разобрано и лежит в `info.data`; если оно само не прошло
        валидацию, его там нет — и сообщать про курсор нечего, про сортировку уже
        сообщено.
        """
        if value is None:
            return None
        sort = info.data.get("sort")
        if not isinstance(sort, str):
            return value
        try:
            decode_cursor(value, parse_sort(sort))
        except InvalidCursorError as error:
            raise PydanticCustomError("cursor", INVALID_CURSOR_MESSAGE) from error
        return value

    @field_validator("account_ids")
    @classmethod
    def _account_ids(cls, value: str | None) -> str | None:
        """Разбор здесь, а не в свойстве: только на границе он даёт 400, а не 500."""
        parts = _split(value)
        if len(parts) > MAX_ACCOUNT_IDS:
            raise PydanticCustomError("account_ids", TOO_MANY_ACCOUNT_IDS_ERROR)
        for part in parts:
            try:
                UUID(part)
            except ValueError as error:
                raise PydanticCustomError("account_ids", ACCOUNT_IDS_ERROR) from error
        return value

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: str | None) -> str | None:
        parts = _split(value)
        if len(parts) > MAX_TAGS:
            raise PydanticCustomError("tags", TOO_MANY_TAGS_ERROR)
        if any(len(part) > MAX_TAG_LENGTH for part in parts):
            raise PydanticCustomError("tags", TAG_TOO_LONG_ERROR)
        return value

    @model_validator(mode="after")
    def _range_is_not_empty(self) -> PositionsQuery:
        """Перевёрнутый период — ошибка, а не пустой журнал.

        Пустой список в ответ на `from > to` человек читает как «сделок нет», а не как
        «границы перепутаны», и ищет пропажу в данных.
        """
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from >= self.date_to
        ):
            raise PydanticCustomError("range", RANGE_ERROR)
        return self

    @property
    def sort_key(self) -> Sort:
        return parse_sort(self.sort)

    @property
    def cursor_key(self) -> Cursor | None:
        """Разобранный курсор. Валидация прошла — значит разбор здесь уже не падает."""
        if self.cursor is None:
            return None
        return decode_cursor(self.cursor, self.sort_key)

    @property
    def account_id_list(self) -> list[UUID]:
        """Пусто — «все неархивированные счета» (SPEC.md 5.1)."""
        return [UUID(part) for part in _split(self.account_ids)]

    @property
    def tag_list(self) -> list[str]:
        return _split(self.tags)


class AccountBrief(BaseModel):
    """Счёт в строке журнала — SPEC.md 5.4: «account {id,label,color,is_demo}»."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    label: str
    color: str
    is_demo: bool

    @classmethod
    def from_account(cls, account: account_models.TradingAccount) -> AccountBrief:
        return cls(id=account.id, label=account.label, color=account.color, is_demo=account.is_demo)


class JournalEntryBrief(BaseModel):
    """Запись журнала «кратко» (SPEC.md 5.4): теги и одна строка заметки."""

    model_config = ConfigDict(extra="forbid")

    tags: list[str]
    has_notes: bool
    notes_preview: str | None
    risk_amount: Money | None
    updated_at: UtcDatetime

    @classmethod
    def from_entry(cls, entry: models.JournalEntry) -> JournalEntryBrief:
        return cls(
            tags=list(entry.tags),
            has_notes=bool(entry.notes and entry.notes.strip()),
            notes_preview=notes_preview(entry.notes),
            risk_amount=entry.risk_amount,
            updated_at=entry.updated_at,
        )


class JournalEntryDetail(BaseModel):
    """Запись журнала целиком — блок карточки (SPEC.md 9.3)."""

    model_config = ConfigDict(extra="forbid")

    notes: str | None
    tags: list[str]
    planned_entry: Quantity | None
    planned_sl: Quantity | None
    planned_tp: Quantity | None
    risk_amount: Money | None
    updated_at: UtcDatetime

    @classmethod
    def from_entry(cls, entry: models.JournalEntry) -> JournalEntryDetail:
        return cls(
            notes=entry.notes,
            tags=list(entry.tags),
            planned_entry=entry.planned_entry,
            planned_sl=entry.planned_sl,
            planned_tp=entry.planned_tp,
            risk_amount=entry.risk_amount,
            updated_at=entry.updated_at,
        )


class ReflectionBrief(BaseModel):
    """SPEC.md 5.4 обещает в списке ровно `reflection.filled_at` — им и ограничиваемся."""

    model_config = ConfigDict(extra="forbid")

    filled_at: UtcDatetime | None

    @classmethod
    def from_reflection(cls, reflection: models.Reflection) -> ReflectionBrief:
        return cls(filled_at=reflection.filled_at)


class ReflectionDetail(BaseModel):
    """Рефлексия целиком. Значения — из словарей SPEC.md 3.5, их отдаёт `/journal/vocab`."""

    model_config = ConfigDict(extra="forbid")

    setup_grade: Grade | None
    execution_grade: Grade | None
    followed_plan: bool | None
    emotion_before: str | None
    emotion_during: str | None
    emotion_after: str | None
    mistakes: list[str]
    confidence: int | None
    free_text: str | None
    filled_at: UtcDatetime | None
    updated_at: UtcDatetime

    @classmethod
    def from_reflection(cls, reflection: models.Reflection) -> ReflectionDetail:
        return cls(
            setup_grade=reflection.setup_grade,  # type: ignore[arg-type]
            execution_grade=reflection.execution_grade,  # type: ignore[arg-type]
            followed_plan=reflection.followed_plan,
            emotion_before=reflection.emotion_before,
            emotion_during=reflection.emotion_during,
            emotion_after=reflection.emotion_after,
            mistakes=list(reflection.mistakes),
            confidence=reflection.confidence,
            free_text=reflection.free_text,
            filled_at=reflection.filled_at,
            updated_at=reflection.updated_at,
        )


class PositionFields(BaseModel):
    """Сама позиция — колонки SPEC.md 3.3 плюс вычисленный `result`.

    Общая база списка и карточки: две модели с разными наборами полей позиции означали бы,
    что таблица и карточка показывают разные числа за одно и то же.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    position_id: int = Field(description="Идентификатор позиции у брокера")
    symbol_raw: str
    symbol_norm: str
    direction: PositionDirection
    status: PositionStatus
    result: PositionResult | None = Field(description="Только у закрытых позиций")
    open_time: UtcDatetime
    close_time: UtcDatetime | None
    volume_opened: Quantity
    volume_closed: Quantity
    avg_entry_price: Quantity
    avg_exit_price: Quantity | None
    gross_pnl: Money
    commission: Money
    swap: Money
    fee: Money
    net_pnl: Money
    deals_count: int
    duration_seconds: int | None
    close_reason: str | None
    is_manual: bool
    rebuilt_at: UtcDatetime

    @staticmethod
    def _position_fields(position: ingest_models.Position) -> dict[str, object]:
        return {
            "id": position.id,
            "position_id": position.position_id,
            "symbol_raw": position.symbol_raw,
            "symbol_norm": position.symbol_norm,
            "direction": position.direction,
            "status": position.status,
            "result": position_result(position),
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
            "is_manual": position.is_manual,
            "rebuilt_at": position.rebuilt_at,
        }


class PositionListItem(PositionFields):
    """Строка журнала — SPEC.md 5.4."""

    account: AccountBrief
    journal_entry: JournalEntryBrief | None
    reflection: ReflectionBrief | None
    attachments_count: int

    @classmethod
    def from_row(
        cls,
        position: ingest_models.Position,
        account: account_models.TradingAccount,
        entry: models.JournalEntry | None,
        reflection: models.Reflection | None,
        attachments_count: int,
    ) -> PositionListItem:
        return cls(
            **cls._position_fields(position),  # type: ignore[arg-type]
            account=AccountBrief.from_account(account),
            journal_entry=None if entry is None else JournalEntryBrief.from_entry(entry),
            reflection=(
                None if reflection is None else ReflectionBrief.from_reflection(reflection)
            ),
            attachments_count=attachments_count,
        )


class DealResponse(BaseModel):
    """Сделка позиции. `raw` и `time_server` наружу не выходят — это отладка (SPEC.md 3.3)."""

    model_config = ConfigDict(extra="forbid")

    deal_ticket: int
    order_ticket: int | None
    symbol_raw: str
    deal_type: str
    entry: str
    reason: str | None
    volume: Quantity
    price: Quantity
    profit: Money
    commission: Money
    swap: Money
    fee: Money
    time_utc: UtcDatetime
    comment: str | None
    magic: int | None
    source: str

    @classmethod
    def from_deal(cls, deal: ingest_models.Deal) -> DealResponse:
        return cls(
            deal_ticket=deal.deal_ticket,
            order_ticket=deal.order_ticket,
            symbol_raw=deal.symbol_raw,
            deal_type=deal.deal_type,
            entry=deal.entry,
            reason=deal.reason,
            volume=deal.volume,
            price=deal.price,
            profit=deal.profit,
            commission=deal.commission,
            swap=deal.swap,
            fee=deal.fee,
            time_utc=deal.time_utc,
            # Комментарий пишет терминал, а показываем его мы: тот же санитайзер, что
            # у `status_message` и `sync_runs.error` (X-21).
            comment=sanitize_external_text(deal.comment),
            magic=deal.magic,
            source=deal.source,
        )


class PositionCard(PositionFields):
    """Карточка позиции — SPEC.md 5.4.

    ⚠️ Вложений здесь пока нет списком, только счётчик: presigned GET требует S3, а его
    в проекте нет до `S2-04`. Поле `attachments` добавит она же.
    """

    account: AccountBrief
    journal_entry: JournalEntryDetail | None
    reflection: ReflectionDetail | None
    attachments_count: int
    deals: list[DealResponse]

    @classmethod
    def from_row(
        cls,
        position: ingest_models.Position,
        account: account_models.TradingAccount,
        entry: models.JournalEntry | None,
        reflection: models.Reflection | None,
        attachments_count: int,
        deals: list[ingest_models.Deal],
    ) -> PositionCard:
        return cls(
            **cls._position_fields(position),  # type: ignore[arg-type]
            account=AccountBrief.from_account(account),
            journal_entry=None if entry is None else JournalEntryDetail.from_entry(entry),
            reflection=(
                None if reflection is None else ReflectionDetail.from_reflection(reflection)
            ),
            attachments_count=attachments_count,
            deals=[DealResponse.from_deal(deal) for deal in deals],
        )


class PositionsPage(BaseModel):
    """Страница списка — конверт SPEC.md 5.1.

    Общего числа строк здесь нет намеренно: `count(*)` по журналу стоит столько же, сколько
    сама страница, а нужен он одному месту — шапке журнала, которая берёт числа из
    `GET /analytics/summary` (S2-05).
    """

    model_config = ConfigDict(extra="forbid")

    items: list[PositionListItem]
    next_cursor: str | None = Field(
        description="Курсор следующей страницы. `null` — страница последняя"
    )
