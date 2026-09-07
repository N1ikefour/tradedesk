"""Тело батча `POST /ingest/deals` — граница между коллектором и API (SPEC.md 5.3).

Источник истины — эти модели. `packages/shared-schemas/ingest-deals.schema.json`
собирается из них (`schema_export.py`) и коммитится: контракт нужен читателям вне
Python (советник MQL5, этап 4), но второй рукописной копии формы в проекте нет —
она разъехалась бы молча. Расхождение файла с моделями делает красным
`tests/unit/test_ingest_schema_contract.py`.

Здесь только форма и её проверка. Числовые коды MT5 (`type`, `entry`, `reason`)
принимаются как есть; их перевод в доменные значения — нормализатор (S1-02).
Лимит батча тут намеренно не проверяется, см. `MAX_DEALS_PER_BATCH`.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, WithJsonSchema, field_validator
from pydantic_core import PydanticCustomError
from pydantic_core.core_schema import ValidationInfo

# SPEC.md 5.3, пункт 1: батч больше этого — 413. Проверка живёт в маршруте (S1-04), а не
# здесь и не в схеме: pydantic отверг бы такой батч как невалидный, то есть 400, а 413 —
# про объём того, что сервер готов обработать, а не про форму документа. Один документ не
# может быть одновременно «неправильной формы» и «слишком большим»; выбран второй ответ,
# потому что его требует спека.
#
# Считать сделки можно только по разобранной модели: их числа в Content-Length нет. Значит
# батч из 5001 сделки будет провалидирован целиком и отвергнут уже после этого — «отклоняет,
# не разбирая» контракт не обещает. Потолок на размер тела до парсинга эту проверку не
# заменяет и нужен S1-04 отдельно: иначе любой отправитель заставляет сервер разобрать тело
# произвольного объёма, и никакой лимит по числу сделок от этого не спасает.
MAX_DEALS_PER_BATCH = 5000

# Границы колонок из SPEC.md 2.2: деньги — numeric(18,2), цены и объёмы — numeric(18,8).
# Значение вне них не влезает в колонку, и без проверки на границе оно доехало бы до
# Postgres и вернулось пользователю пятисоткой вместо 400 с именем поля.
MONEY_LIMIT = 10**16
QUANTITY_LIMIT = 10**10
# То же самое для целых: тикеты, `position_id` и `magic` лежат в bigint (`models.py`),
# а bigint знаковый. Верхняя граница здесь — единственное, что отделяет 400 с именем поля
# от пятисотки на вставке.
MAX_BIGINT = 2**63 - 1

SERVER_TIME_ERROR = (
    "Время сервера брокера передаётся без часового пояса, "
    "в формате YYYY-MM-DDTHH:MM:SS (см. SPEC.md 6.3)"
)
TIME_MSC_ERROR = "time_msc и time_server описывают разные моменты"

# Ровно одна каноническая форма: дата, `T`, время, необязательные доли секунды.
# Ни `Z`, ни `+03:00`, ни пробела вместо `T`. Суффикс зоны отвергается, а не
# отбрасывается: «14:03:11Z» и «14:03:11» — разные моменты, и угадать, что имел в виду
# отправитель, нельзя, а ошибка на пару часов переносит сделку в соседний торговый день.
SERVER_TIME_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?$"
_SERVER_TIME_RE = re.compile(SERVER_TIME_PATTERN)

# Символ брокера: без пробелов, непустой. Нормализация суффиксов — S1-07.
SYMBOL_PATTERN = r"^\S+$"
# У сделки символа может не быть вовсе: неторговым операциям терминал кладёт в это поле
# пустую строку (X-44, выгрузка 7 сентября 2026). Пустоту разрешает шаблон, а не
# `min_length`, потому что запрет остаётся — он просто перестал быть безусловным, см.
# `TRADING_DEAL_TYPE_CODES`. У открытой позиции символ есть всегда, там SYMBOL_PATTERN.
DEAL_SYMBOL_PATTERN = r"^\S*$"
# Комментарий брокера уходит в логи и в UI; управляющие символы там не нужны.
COMMENT_PATTERN = r"^[^\x00-\x1f\x7f]*$"

# Коды `DEAL_TYPE_*`, у которых инструмент обязан быть: BUY и SELL. Всё остальное —
# пополнение, кредит, начисление, — операции над счётом, а не над инструментом.
#
# Набор продублирован из SPEC.md 6.2 (маппинг живёт в `normalizer.py`) не по недосмотру:
# граница не вправе импортировать нормализатор — он импортирует её. Чтобы копия не
# разошлась с оригиналом, обе стороны сверяет `tests/unit/test_normalizer.py`.
TRADING_DEAL_TYPE_CODES = frozenset({0, 1})

TRADING_SYMBOL_ERROR = (
    "Торговая сделка обязана нести инструмент; пустой symbol допустим "
    "только у неторговых операций (SPEC.md 6.2)"
)

# То же правило для опубликованного файла контракта. Условие draft-07 выражает, значит
# файл обязан его нести: советник MQL5 (этап 4) сверяется с файлом, и правило, которого
# в нём нет, приходит к автору необъяснимым 400. Здесь и `_trading_deal_carries_a_symbol`
# — одно правило, записанное дважды; их согласие проверяет
# `tests/unit/test_ingest_schema_contract.py`, а не постулируется.
TRADING_SYMBOL_JSON_SCHEMA_RULE: dict[str, Any] = {
    "allOf": [
        {
            "if": {
                "properties": {"type": {"enum": sorted(TRADING_DEAL_TYPE_CODES)}},
                "required": ["type"],
            },
            "then": {"properties": {"symbol": {"minLength": 1}}},
        }
    ]
}

# Реальный диапазон смещений IANA: от UTC-12:00 до UTC+14:00.
MIN_SERVER_UTC_OFFSET_MINUTES = -720
MAX_SERVER_UTC_OFFSET_MINUTES = 840
SERVER_UTC_OFFSET_STEP_MINUTES = 15


def _parse_server_time(value: object) -> object:
    """Наивное время сервера брокера. Осознанно узкий вход, см. `SERVER_TIME_PATTERN`."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            raise PydanticCustomError("server_time", SERVER_TIME_ERROR)
        return value
    if not isinstance(value, str) or _SERVER_TIME_RE.match(value) is None:
        raise PydanticCustomError("server_time", SERVER_TIME_ERROR)
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:  # «2026-13-45T00:00:00» — форма верна, даты не существует
        raise PydanticCustomError("server_time", SERVER_TIME_ERROR) from error


# Деньги и объёмы приезжают в Decimal, а не в float: сумма float по сотням сделок уезжает,
# а S1-12 требует схождения с отчётом терминала в 0,00. JSON-число pydantic переводит в
# Decimal через кратчайшее представление float, то есть точно для всего, что укладывается
# в ~17 значащих цифр (цены и деньги укладываются). Строка проходит вообще без float —
# отправителю, которому нужна побитовая точность, схема разрешает строку.
Money = Annotated[Decimal, Field(allow_inf_nan=False, gt=-MONEY_LIMIT, lt=MONEY_LIMIT)]
# Объёмы, цены, уровни SL/TP: отрицательных не бывает, 0 — «не задано».
Quantity = Annotated[Decimal, Field(allow_inf_nan=False, ge=0, lt=QUANTITY_LIMIT)]
# Целое, которое доезжает до колонки bigint: тикеты, `position_id`, `magic`. `le`, а не
# `lt`: в опубликованный файл уходит `maximum` с самим предельным значением, и читатель
# видит границу колонки, а не соседнее с ней число.
Bigint = Annotated[int, Field(ge=0, le=MAX_BIGINT)]

# Кратность 15 выражена `multiple_of`, а не проверкой в коде: правило обязано доехать до
# опубликованного файла. Контракт объявляет `source: "ea" | "csv"`, то есть отправителей
# вне Python; советник, сверившийся с файлом, прислал бы offset 7 и получил 400 за то,
# чего файл не запрещал. Цена — английский текст pydantic в `details.fields` вместо своего;
# у соседних `ge`/`le` он и так английский, а правило по-русски остаётся в `description`.
ServerUtcOffsetMinutes = Annotated[
    int,
    Field(
        ge=MIN_SERVER_UTC_OFFSET_MINUTES,
        le=MAX_SERVER_UTC_OFFSET_MINUTES,
        multiple_of=SERVER_UTC_OFFSET_STEP_MINUTES,
    ),
]

# WithJsonSchema, а не format: date-time: RFC 3339 требует смещения, а мы его как раз
# запрещаем. Опубликованный контракт обязан описывать то, что принимает сервер, поэтому
# в схему уходит тот же самый шаблон, по которому валидирует pydantic.
ServerTime = Annotated[
    datetime,
    BeforeValidator(_parse_server_time),
    WithJsonSchema({"type": "string", "pattern": SERVER_TIME_PATTERN}, mode="validation"),
]


class IngestBase(BaseModel):
    """Общая настройка: неизвестное поле — ошибка.

    `extra="forbid"` на границе, у которой один производитель — наш коллектор. Опечатка
    в имени поля иначе теряется молча: `commision` вместо `commission` не долетит до БД,
    комиссия сохранится нулём, и расхождение вылезет в сверке недели спустя. Цена решения
    известна: коллектор новее API уронит ингест целиком. Это осознанный размен — они
    ставятся из одного репозитория и обновляются вместе (SETUP.md), а тихо потерянные
    деньги дороже громкой ошибки.
    """

    model_config = ConfigDict(extra="forbid")


class IngestAccountInfo(IngestBase):
    """`mt5.account_info()` в терминах API (SPEC.md 6.1)."""

    currency: str = Field(
        pattern=r"^[A-Z]{3}$",
        description="Валюта счёта, ISO 4217. Не-USD принимается и разбирается доменом (S1-06)",
    )
    # Строка, а не число MT5 (0/1/2), в отличие от type/entry/reason: так в примере
    # SPEC.md 5.3. Значение `exchange` контракт принимает, потому что терминал его отдаёт;
    # что с ним делать при записи в `trading_accounts.account_type` — решает S1-04.
    margin_mode: Literal["netting", "exchange", "hedging"] = Field(
        description="Режим счёта: MT5 `ACCOUNT_MARGIN_MODE` (0 netting, 1 exchange, 2 hedging)"
    )
    balance: Money = Field(description="Баланс счёта в валюте счёта")
    equity: Money = Field(description="Средства счёта в валюте счёта")


class IngestDeal(IngestBase):
    """Одна сделка из `mt5.history_deals_get()` как есть, без нормализации (SPEC.md 6.1)."""

    model_config = ConfigDict(json_schema_extra=TRADING_SYMBOL_JSON_SCHEMA_RULE)

    ticket: Bigint = Field(description="Тикет сделки, уникален в пределах счёта")
    order: Bigint = Field(description="Тикет ордера; 0, если ордера нет")
    position_id: Bigint = Field(description="Идентификатор позиции MT5; 0 у balance/credit")
    # Объявлен раньше `symbol`: правило ниже читает уже проверенный код типа.
    type: int = Field(
        ge=0, description="MT5 `DEAL_TYPE_*`. Неизвестный код нормализуется в 'other' (SPEC.md 6.2)"
    )
    symbol: str = Field(
        max_length=64,
        pattern=DEAL_SYMBOL_PATTERN,
        description=(
            "Символ как у брокера, с суффиксом: 'EURUSD.m'. Пустой — только у неторговой "
            "операции (пополнение, кредит, начисление): инструмента у неё нет"
        ),
    )
    # 0..3 — весь ENUM_DEAL_ENTRY. Запаса «прочее» у entry нет: SPEC.md 6.2 не даёт для него
    # значения по умолчанию, а `deals.entry` — NOT NULL. Код вне диапазона означает, что
    # коллектор прислал не тот enum, и молча превратить его во что-то — испортить позицию.
    entry: int = Field(ge=0, le=3, description="MT5 `DEAL_ENTRY_*`: 0 in, 1 out, 2 inout, 3 out_by")
    reason: int = Field(
        ge=0, description="MT5 `DEAL_REASON_*`. Неизвестный код нормализуется в 'other'"
    )
    volume: Quantity = Field(description="Объём сделки в лотах")
    price: Quantity = Field(description="Цена исполнения")
    profit: Money = Field(description="Финансовый результат сделки, знак как у брокера")
    commission: Money = Field(description="Комиссия, знак как у брокера")
    swap: Money = Field(description="Своп, знак как у брокера")
    fee: Money = Field(description="Сбор, знак как у брокера")
    # Объявлено раньше time_msc: сверка ниже читает уже проверенное значение.
    time_server: ServerTime = Field(
        description="Время сервера брокера, без часового пояса (SPEC.md 6.3)"
    )
    time_msc: int = Field(
        ge=0,
        description=(
            "Тот же момент в миллисекундах эпохи по часам сервера брокера. "
            "Обязан совпадать с `time_server` с точностью до секунды"
        ),
    )
    comment: str = Field(
        max_length=255,
        pattern=COMMENT_PATTERN,
        description="Комментарий брокера, может быть пустым",
    )
    magic: Bigint = Field(description="Magic number советника; 0 у ручной торговли")

    @field_validator("symbol")
    @classmethod
    def _trading_deal_carries_a_symbol(cls, value: str, info: ValidationInfo) -> str:
        """Пустой символ разрешён неторговой операции и только ей (X-44).

        Депозит приходит с `symbol = ''`, и безусловный `min_length=1` отвергал им весь
        батч: у любого, кто хоть раз пополнял счёт, синхронизация не проходила никогда и
        ретраем не чинилась — депозит из истории никуда не девается.

        Послабление сделано зависимым от типа, а не общим. Общее увело бы проверку с
        границы в нормализатор (CLAUDE.md §5), а торговая сделка без инструмента — это
        уже потеря данных: позиция собралась бы без символа, и в журнале появилась бы
        строка, про которую неизвестно, чем торговали.
        """
        deal_type = info.data.get("type")
        if value == "" and isinstance(deal_type, int) and deal_type in TRADING_DEAL_TYPE_CODES:
            raise PydanticCustomError("trading_symbol", TRADING_SYMBOL_ERROR)
        return value

    @field_validator("time_msc")
    @classmethod
    def _agrees_with_time_server(cls, value: int, info: ValidationInfo) -> int:
        """Два источника правды про один момент обязаны сходиться.

        MT5 отдаёт `deal.time` и `deal.time_msc` для одного события, поэтому
        `time_msc // 1000` равно эпохе `time_server`. Расхождение означает, что батч
        собран из разных сделок или из разных полей — а неверное время уводит позицию в
        чужой торговый день, где её никто не найдёт. Молчаливого «верим первому» здесь
        быть не может: неизвестно, какое из двух значений правда.
        """
        server = info.data.get("time_server")
        if not isinstance(server, datetime):  # time_server не прошёл — своя ошибка уже есть
            return value
        if value // 1000 != int(server.replace(tzinfo=UTC).timestamp()):
            raise PydanticCustomError("time_msc", TIME_MSC_ERROR)
        return value


class IngestOpenPosition(IngestBase):
    """Открытая позиция из `mt5.positions_get()` (SPEC.md 5.3, пункт 5)."""

    position_id: Bigint = Field(description="Идентификатор позиции MT5")
    symbol: str = Field(min_length=1, max_length=64, pattern=SYMBOL_PATTERN, description="Символ")
    # Здесь ENUM_POSITION_TYPE, а не DEAL_TYPE: других значений у открытой позиции нет,
    # и код вне 0/1 означает, что коллектор перепутал перечисления.
    type: Literal[0, 1] = Field(description="MT5 `POSITION_TYPE_*`: 0 buy, 1 sell")
    volume: Quantity = Field(description="Текущий объём позиции в лотах")
    price_open: Quantity = Field(description="Средняя цена входа")
    time_server: ServerTime = Field(description="Время открытия по часам сервера брокера")
    sl: Quantity = Field(description="Stop Loss; 0 — не выставлен")
    tp: Quantity = Field(description="Take Profit; 0 — не выставлен")
    profit: Money = Field(description="Текущий незафиксированный результат")


class IngestDealsBatch(IngestBase):
    """Батч ингеста: `POST /ingest/deals` (SPEC.md 5.3).

    `deals` и `open_positions` обязательны и могут быть пустыми. Пустой список и
    отсутствующее поле — разные утверждения: `"open_positions": []` означает «на счёте
    открытых позиций нет», и сборщик по нему закрывает позиции (SPEC.md 7). Разреши мы
    пропускать поле — «не прислал» стало бы неотличимо от «нет открытых», и позиции
    закрывались бы на батче, который про них ничего не знал.
    """

    account_id: UUID = Field(description="Счёт, которому принадлежит батч")
    # `manual` из словаря `deals.source` тут отсутствует: ручные сделки заводятся через
    # POST /journal/positions/manual (SPEC.md 5.4) и помечаются `positions.is_manual`.
    # Приняв `manual` здесь, мы дали бы обойти этот флаг.
    source: Literal["collector", "ea", "csv"] = Field(description="Кто прислал батч")
    server_utc_offset_minutes: ServerUtcOffsetMinutes = Field(
        description=(
            "Смещение часов сервера брокера от UTC в минутах, кратное "
            f"{SERVER_UTC_OFFSET_STEP_MINUTES} (SPEC.md 6.3): все реальные зоны кратны, "
            "и некратное значение означает, что в поле уехали не минуты. "
            "`time_utc = time_server − offset`"
        ),
    )
    account_info: IngestAccountInfo = Field(description="Состояние счёта на момент батча")
    deals: list[IngestDeal] = Field(
        description=(
            "Сделки окна синхронизации; перекрытие с прошлым батчем — норма. "
            f"Не больше {MAX_DEALS_PER_BATCH} штук: батч большего размера сервер "
            "отвергает с HTTP 413"
        )
    )
    open_positions: list[IngestOpenPosition] = Field(
        description="Все открытые позиции счёта на момент батча; пустой список — открытых нет"
    )


class IngestDealsResponse(IngestBase):
    """Ответ `POST /ingest/deals` — ровно пять полей SPEC.md 5.3, пункт 7.

    В опубликованный `ingest-deals.schema.json` эта модель не входит: файл описывает
    **тело батча**, то есть то, что обязан уметь собрать отправитель вне Python
    (советник MQL5, этап 4). Ответ он читает по OpenAPI, как и фронт.

    Шестого поля здесь нет намеренно, хотя место для него есть: группы сделок, которые
    сегодня не складываются в позицию (одни корректировки без входа, S1-04), в ответ не
    попадают — перечень полей задан спекой, а расширять его молча значит расходиться с
    ней. Такие группы уходят в лог событием `ingest.position_unbuildable`.
    """

    received: int = Field(ge=0, description="Сколько сделок пришло в батче")
    inserted: int = Field(ge=0, description="Сколько сделок оказалось новыми")
    duplicates: int = Field(ge=0, description="Сколько уже было в базе: `received − inserted`")
    positions_rebuilt: int = Field(ge=0, description="Сколько строк `positions` пересобрано")
    sync_run_id: int = Field(description="Строка `sync_runs` этого батча")


def batch_json_schema() -> dict[str, Any]:
    """JSON Schema батча в диалекте pydantic. Перевод в draft-07 — `schema_export.py`."""
    return IngestDealsBatch.model_json_schema(
        by_alias=True, ref_template="#/definitions/{model}", mode="validation"
    )
