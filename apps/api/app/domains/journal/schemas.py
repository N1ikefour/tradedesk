"""Тела запросов и ответов журнала — SPEC.md 5.4.

Модели ответа собираются полем за полем в `from_*`, а не `model_validate` поверх
ORM-объекта, по той же причине, что и в домене счетов: список полей ответа должен быть
явным текстом, который видно в диффе. Здесь это важнее, чем кажется, — в `deals` лежит
колонка `raw` с полным ответом терминала, и `model_validate` вынес бы её наружу целиком
первым же добавлением поля в модель.

Деньги, цены и объёмы уходят строками (`core.schemas.MoneyOut`, `QuantityOut`): в JSON нет
десятичного типа, и число здесь означало бы double на фронте (`CLAUDE.md` §2 — никакого
float в денежных расчётах).

⚠️ **У всех тел записи в этом файле поля обязательны — без исключений.** `PUT` из
SPEC.md 5.4 заменяет запись целиком, поэтому отсутствие поля означало бы «сотри его».
Автосохранение карточки (`S2-07`) с частичным телом стёрло бы заметку без единого
признака ошибки; с обязательными полями тот же запрос — `400 validation_error` с именем
пропущенного поля. Очистка выражается явным `null` (у массивов — пустым массивом).
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.core.schemas import MoneyOut, QuantityOut, UtcDatetime
from app.core.text import sanitize_external_text
from app.domains.accounts import models as account_models
from app.domains.ingest import models as ingest_models
from app.domains.ingest import schemas as ingest_schemas
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
from app.domains.journal.vocab import (
    CONFIDENCE_MAX,
    CONFIDENCE_MIN,
    EMOTIONS,
    EXECUTION_GRADES,
    MISTAKES,
    SETUP_GRADES,
    Emotion,
    Grade,
    Mistake,
)

PositionStatus = Literal["open", "closed"]
PositionDirection = Literal["long", "short"]
# SPEC.md 5.4: «result считается по net_pnl: > 0 win, < 0 loss, = 0 breakeven».
PositionResult = Literal["win", "loss", "be"]

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
    risk_amount: MoneyOut | None
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
    planned_entry: QuantityOut | None
    planned_sl: QuantityOut | None
    planned_tp: QuantityOut | None
    risk_amount: MoneyOut | None
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
    volume_opened: QuantityOut
    volume_closed: QuantityOut
    avg_entry_price: QuantityOut
    avg_exit_price: QuantityOut | None
    gross_pnl: MoneyOut
    commission: MoneyOut
    swap: MoneyOut
    fee: MoneyOut
    net_pnl: MoneyOut
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
    volume: QuantityOut
    price: QuantityOut
    profit: MoneyOut
    commission: MoneyOut
    swap: MoneyOut
    fee: MoneyOut
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


# --- запись: entry, reflection, теги, словари (S2-02) --------------------------

# Ограничения на длину текста — не про показ, а про то, что тело запроса не транспорт для
# дампа: без них одна заметка кладёт в `text` сколько угодно мегабайт, и каждая страница
# журнала потом тащит их через `notes_preview`.
MAX_NOTES_LENGTH = 20_000
MAX_FREE_TEXT_LENGTH = 20_000

# Границы колонок берутся у ingest, а не переписываются: `numeric(18,2)` и `numeric(18,8)`
# — одни и те же колонки SPEC.md 2.2, и вторая копия чисел разошлась бы молча. Имена
# намеренно свои: `Money`/`Quantity` из ingest проверяют присланное коллектором, здесь —
# другое поле и другие правила (`risk_amount` строго положителен, цены плана — нет).
MONEY_LIMIT = ingest_schemas.MONEY_LIMIT
QUANTITY_LIMIT = ingest_schemas.QUANTITY_LIMIT

TAG_COLOR_PATTERN = r"^#[0-9a-f]{6}$"
_TAG_COLOR_RE = re.compile(TAG_COLOR_PATTERN)

# Postgres не хранит нулевой байт в `text`: asyncpg роняет запрос уже на драйвере, то есть
# это была бы 500 на обычной вставке текста. Остальные управляющие символы в заметке
# законны — она многострочная.
NUL = "\x00"

# Одиночные строки, которые едут в чипы и в фильтр: здесь управляющие символы не нужны.
_TAG_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")

NOTES_TOO_LONG_ERROR = f"Заметка не длиннее {MAX_NOTES_LENGTH} символов"
FREE_TEXT_TOO_LONG_ERROR = f"Текст не длиннее {MAX_FREE_TEXT_LENGTH} символов"
NUL_ERROR = "Текст не должен содержать нулевой байт"
TAG_REQUIRED_ERROR = "Тег не может быть пустым"
TAG_CONTROL_ERROR = "Тег не должен содержать управляющие символы"
# Запятая — разделитель в `?tags=a,b` (фильтр списка). Тег с запятой сохранился бы, но
# отфильтровать по нему стало бы нечем: человек видел бы чип, по которому ничего не ищется.
TAG_COMMA_ERROR = "Тег не может содержать запятую: по ней разделяется фильтр ?tags="
TOO_MANY_ENTRY_TAGS_ERROR = f"Не больше {MAX_TAGS} тегов на позиции"
TAG_COLOR_ERROR = "Цвет тега — шестизначный hex в нижнем регистре, например #2563eb, либо null"
CONFIDENCE_ERROR = f"Уверенность — целое от {CONFIDENCE_MIN} до {CONFIDENCE_MAX}"

# Тела запросов принимают и число, и строку — как и контракт ингеста (SPEC.md 5.3).
# Наружу то же самое уходит только строкой (`MoneyOut`, `QuantityOut`): в JSON нет
# десятичного типа, и клиенту, которому нужна точность, строка доступна в обе стороны.
PlannedPrice = Annotated[Decimal, Field(allow_inf_nan=False, gt=-QUANTITY_LIMIT, lt=QUANTITY_LIMIT)]
# Строго положителен, и это не вкус: SPEC.md 3.4 — «если задано, R считается от него»,
# то есть ноль здесь стал бы делением на ноль в метриках (S2-05), а отрицательный риск
# перевернул бы знак R. «Не задано» выражается `null`, а не нулём.
RiskAmount = Annotated[Decimal, Field(allow_inf_nan=False, gt=0, lt=MONEY_LIMIT)]


def _reject_nul(value: str, code: str) -> str:
    if NUL in value:
        raise PydanticCustomError(code, NUL_ERROR)
    return value


def _clean_long_text(value: str | None, code: str, limit: int, too_long: str) -> str | None:
    """Свободный текст: пробелы по краям срезаются, пустой становится `null`.

    Строка из одних пробелов — это отсутствие текста, а не текст. Разница видна снаружи:
    от неё зависит `has_notes` в списке и `filled_at` у рефлексии.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    # Длина раньше поиска по строке: мегабайтное значение не должно доходить до сканирования.
    if len(text) > limit:
        raise PydanticCustomError(code, too_long)
    return _reject_nul(text, code)


def normalize_tag(value: str) -> str:
    """Один тег в каноничном виде ввода: обрезанный, без управляющих символов и запятых.

    Регистр **сохраняется**: показывается то, что напечатал человек. Сведение `Trend` и
    `trend` к одной записи словаря — не здесь, а в сервисе: для этого нужен сам словарь.
    """
    tag = value.strip()
    if not tag:
        raise PydanticCustomError("tags", TAG_REQUIRED_ERROR)
    if len(tag) > MAX_TAG_LENGTH:
        raise PydanticCustomError("tags", TAG_TOO_LONG_ERROR)
    if FILTER_SEPARATOR in tag:
        raise PydanticCustomError("tags", TAG_COMMA_ERROR)
    if _TAG_CONTROL_RE.search(tag):
        raise PydanticCustomError("tags", TAG_CONTROL_ERROR)
    return tag


def fold_tag(value: str) -> str:
    """Ключ сравнения тегов. `casefold`, а не `lower`: словарь пользователя русский тоже.

    ⚠️ Складывается только регистр, и этого мало для «выглядят одинаково». Юникод сюда
    доезжает как есть: NFKC-нормализации нет, поэтому `Trend` латиницей и `Тrend` с
    кириллической `Т` — два разных тега. Так же проходят невидимки и переопределители
    направления — `U+200B`, `U+202E`, а внутри строки и `U+2028/29`: `_TAG_CONTROL_RE`
    ловит только C0/C1, а `strip` в `normalize_tag` снимает по краям лишь то, что Python
    считает пробелом. В обратную сторону `casefold` складывает больше, чем ждёшь: `ß` и
    `SS` — один ключ.

    Дырой это не является: словарь висит на `tags.user_id`, чужого тега им не достать и
    не подменить — обмануть можно только себя. Но два одинаковых на вид чипа в `S2-06`
    объясняются именно этим, и искать причину надо здесь.
    """
    return value.casefold()


def normalize_tag_list(value: list[str]) -> list[str]:
    """Теги позиции: нормализованные, без повторов без учёта регистра, в порядке ввода.

    Повтор — не ошибка: `["Trend", "trend"]` это один тег, названный дважды, и 400 здесь
    был бы придиркой. Побеждает первое написание в списке; какое написание доедет до
    хранения, решает словарь (см. `service.resolve_tags`).
    """
    unique: dict[str, str] = {}
    for raw in value:
        tag = normalize_tag(raw)
        unique.setdefault(fold_tag(tag), tag)
    if len(unique) > MAX_TAGS:
        raise PydanticCustomError("tags", TOO_MANY_ENTRY_TAGS_ERROR)
    return list(unique.values())


def validate_tag_color(value: str | None) -> str | None:
    """`null` или `#rrggbb` в нижнем регистре — и ничего больше.

    Не палитра из восьми цветов, как у счетов: тегов бывает много, и восьми им мало.
    Но и не свободная строка: значение уезжает во фронт как цвет чипа, то есть в `style`,
    и произвольный текст оттуда — это то, что там оказаться не должно.
    """
    if value is None:
        return None
    color = value.strip().lower()
    if not color:
        return None
    if _TAG_COLOR_RE.match(color) is None:
        raise PydanticCustomError("color", TAG_COLOR_ERROR)
    return color


class JournalEntryUpdate(BaseModel):
    """Тело `PUT /journal/positions/{id}/entry` — полная замена записи журнала.

    ⚠️ **Все поля обязательны.** Это не придирка к форме, а единственная защита от того,
    ради чего маршрут и существует: `PUT` заменяет запись целиком, поэтому тело без
    `notes` означает «сотри заметку». Автосохранение карточки (`S2-07`), приславшее
    частичное тело, молча уничтожило бы написанное — и человек узнал бы об этом при
    следующем открытии позиции. С обязательными полями такой запрос — `400
    validation_error` с именем пропущенного поля в `details.fields`, то есть ошибка
    клиента, видимая в разработке, а не потеря данных у пользователя.

    Очистка поля выражается явным `null` (у `tags` — пустым массивом). Разница между
    «не прислал» и «прислал null» здесь единственное, что отделяет ошибку от намерения.
    """

    model_config = ConfigDict(extra="forbid")

    notes: str | None = Field(
        description=(
            f"Заметка, не длиннее {MAX_NOTES_LENGTH} символов. "
            "`null` или строка из пробелов очищают заметку"
        )
    )
    tags: list[str] = Field(
        description=(
            f"Теги позиции, не больше {MAX_TAGS}. Пустой массив снимает все теги. "
            "Отсутствующие в словаре заводятся автоматически; написание берётся из "
            "словаря, если тег там уже есть"
        )
    )
    planned_entry: PlannedPrice | None = Field(description="Планируемая цена входа")
    planned_sl: PlannedPrice | None = Field(description="Планируемый стоп-лосс")
    planned_tp: PlannedPrice | None = Field(description="Планируемый тейк-профит")
    risk_amount: RiskAmount | None = Field(
        description="Риск в валюте счёта, строго больше нуля. От него считается R"
    )

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: str | None) -> str | None:
        return _clean_long_text(value, "notes", MAX_NOTES_LENGTH, NOTES_TOO_LONG_ERROR)

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        return normalize_tag_list(value)


class ReflectionUpdate(BaseModel):
    """Тело `PUT /journal/positions/{id}/reflection` — полная замена рефлексии.

    ⚠️ **Все поля обязательны** — по той же причине, что и у записи журнала, см.
    `JournalEntryUpdate`.

    Значения эмоций и ошибок проверяются по словарям SPEC.md 3.5 здесь, на границе:
    ключ вне словаря сохранился бы, но подписи у него на фронте нет, и в карточке он
    остался бы пустым местом, которое нечем объяснить.
    """

    model_config = ConfigDict(extra="forbid")

    setup_grade: Grade | None = Field(description="Оценка сетапа")
    execution_grade: Grade | None = Field(description="Оценка исполнения")
    followed_plan: bool | None = Field(description="Следовал ли плану")
    emotion_before: Emotion | None = Field(description="Эмоция до входа")
    emotion_during: Emotion | None = Field(description="Эмоция в позиции")
    emotion_after: Emotion | None = Field(description="Эмоция после выхода")
    mistakes: list[Mistake] = Field(description="Ошибки из словаря. Пустой массив — их нет")
    confidence: int | None = Field(description=CONFIDENCE_ERROR)
    free_text: str | None = Field(
        description=f"Свободный текст, не длиннее {MAX_FREE_TEXT_LENGTH} символов"
    )

    @field_validator("mistakes")
    @classmethod
    def _mistakes(cls, value: list[Mistake]) -> list[Mistake]:
        """Повторы схлопываются, порядок ввода сохраняется: два одинаковых чипа — один чип.

        Длина после этого не проверяется: значения сужены `Literal` по словарю SPEC.md 3.5,
        и список без повторов длиннее самого словаря быть не может.
        """
        return list(dict.fromkeys(value))

    @field_validator("confidence", mode="before")
    @classmethod
    def _confidence_is_not_bool(cls, value: object) -> object:
        """`true` — не «уверенность 1»: bool в Python наследует int, и pydantic пропустил
        бы его как 1. Клиент получил бы «сохранено» вместо явной ошибки."""
        if isinstance(value, bool):
            raise PydanticCustomError("confidence", CONFIDENCE_ERROR)
        return value

    @field_validator("confidence")
    @classmethod
    def _confidence(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if not CONFIDENCE_MIN <= value <= CONFIDENCE_MAX:
            raise PydanticCustomError("confidence", CONFIDENCE_ERROR)
        return value

    @field_validator("free_text")
    @classmethod
    def _free_text(cls, value: str | None) -> str | None:
        return _clean_long_text(value, "free_text", MAX_FREE_TEXT_LENGTH, FREE_TEXT_TOO_LONG_ERROR)

    @property
    def is_filled(self) -> bool:
        """Есть ли в рефлексии хоть одно заполненное поле — SPEC.md 5.4 про `filled_at`.

        Заполнено — значит человек **сделал выбор**, а не «значение похоже на непустое».
        Отсюда два неочевидных следствия, и оба видны пользователю:

        * `followed_plan = false` — заполнено. Это самый ценный ответ в журнале
          («плану не следовал»), и считать его пустым значило бы гасить иконку рефлексии
          ровно на тех сделках, ради разбора которых журнал и ведут.
        * пустая строка в `free_text` и пустой массив `mistakes` — не заполнено. Выбора
          в них нет: валидатор уже свёл строку из пробелов к `null`, а пустой массив —
          это «ошибок не отмечено», то же самое, что не трогать поле.

        `confidence` в словах не нуждается: его диапазон 1..5, нуля в нём нет.
        """
        return any(
            (
                self.setup_grade is not None,
                self.execution_grade is not None,
                self.followed_plan is not None,
                self.emotion_before is not None,
                self.emotion_during is not None,
                self.emotion_after is not None,
                bool(self.mistakes),
                self.confidence is not None,
                self.free_text is not None,
            )
        )


class TagCreateRequest(BaseModel):
    """Тело `POST /journal/tags` — завести тег или задать существующему написание и цвет.

    ⚠️ **Оба поля обязательны**, как и в остальных телах этой задачи: `color: null`
    очищает цвет, отсутствие поля — ошибка. Иначе «сохранил тег без цвета» и «не трогал
    цвет» выглядели бы одинаково.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description=f"Название тега, не длиннее {MAX_TAG_LENGTH} символов")
    color: str | None = Field(description=TAG_COLOR_ERROR)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return normalize_tag(value)

    @field_validator("color")
    @classmethod
    def _color(cls, value: str | None) -> str | None:
        return validate_tag_color(value)


class TagResponse(BaseModel):
    """Тег словаря пользователя — SPEC.md 3.4."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    color: str | None
    usage_count: int = Field(description="На скольких позициях пользователя стоит этот тег")

    @classmethod
    def from_tag(cls, tag: models.Tag, usage_count: int) -> TagResponse:
        return cls(id=tag.id, name=tag.name, color=tag.color, usage_count=usage_count)


class TagsResponse(BaseModel):
    """Конверт списка SPEC.md 5.1. Курсора нет: словарь тегов человека помещается целиком."""

    model_config = ConfigDict(extra="forbid")

    items: list[TagResponse]


class TagDeletedResponse(BaseModel):
    """Итог `DELETE /journal/tags/{tag_id}`.

    Не `204`: удаление тега из словаря снимает его со **всех** позиций пользователя, и
    сколько их было — единственное, чего клиент не может узнать после факта. Без числа
    интерфейсу нечего показать вместо «удалено», хотя изменились десятки позиций.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Название удалённого тега — для сообщения пользователю")
    positions_updated: int = Field(description="Со скольких позиций тег снят")


class VocabResponse(BaseModel):
    """Словари SPEC.md 3.5. Ключи стабильны, русские подписи — на фронте."""

    model_config = ConfigDict(extra="forbid")

    emotions: list[str]
    mistakes: list[str]
    setup_grades: list[str]
    execution_grades: list[str]

    @classmethod
    def current(cls) -> VocabResponse:
        return cls(
            emotions=list(EMOTIONS),
            mistakes=list(MISTAKES),
            setup_grades=list(SETUP_GRADES),
            execution_grades=list(EXECUTION_GRADES),
        )
