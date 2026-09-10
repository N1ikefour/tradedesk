"""Сырые структуры терминала → тело `POST /ingest/deals`.

Контракт — `packages/shared-schemas/ingest-deals.schema.json` (`S1-01`), и он строже, чем
пример в `SPEC.md` §5.3. Этот модуль — единственное место, где коллектор знает форму
батча, и он **чистый**: на вход идут объекты с нужными атрибутами, на выход — словари.
Терминал сюда не заглядывает, поэтому всё здесь проверяется тестами на машине разработки.

Три решения, которые видно снаружи.

1. **Деньги и объёмы уезжают строками.** Схема разрешает и число, и строку, а строка
   доезжает до `Decimal` вообще без float (`schemas.py` в api). Округления коллектор не
   делает: шум `float64` у брокера (`-1.6099999999999999` вместо `-1.61`) — факт, и
   решение, во что его превратить, принято на сервере (`S1-03`, поштучное округление до
   сложения). Коллектор, округляющий по дороге, был бы вторым местом принятия того же
   решения.
2. **`time_server` берётся из `deal.time`, а не из `time_msc`.** `SPEC.md` §6.3: время
   терминала — «фальшивый UTC», равный часам сервера брокера. Сервер сверяет два поля
   между собой и отвергает батч при расхождении, поэтому расхождение ловится здесь и
   называется по тикету.
3. **Строку, которую сервер точно отвергнет, коллектор не отправляет.** `extra="forbid"`
   и валидаторы границы работают на весь батч разом: одна сделка с пробелом в символе
   означает `400` на все 5000 и остановку синхронизации счёта навсегда, без ретрая.
   Названная потеря одной сделки дешевле молчаливой остановки счёта — но она **обязана**
   быть названной, поэтому отбракованные попадают и в лог, и в heartbeat.

   Отбраковка **симметрична**: то же самое делается с открытыми позициями, и это не
   украшение. Открытые позиции едут в каждом чанке окна, поэтому негодная позиция
   отвергала бы все батчи подряд, а не один. `account_info` выбросить нельзя — без него
   батча нет вовсе, — и непереводимое значение там останавливает синк с названной причиной
   (`UnsendableError` ловит `worker.py`).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final, Protocol

SOURCE_COLLECTOR: Final = "collector"

# MT5 `ACCOUNT_MARGIN_MODE` (SPEC.md 6.1) → значения перечисления контракта.
MARGIN_MODES: Final[dict[int, str]] = {0: "netting", 1: "exchange", 2: "hedging"}

# MT5 `DEAL_TYPE_BUY` / `DEAL_TYPE_SELL`. У них символ обязан быть непустым — граница
# отвергает торговую сделку без инструмента (`X-44`).
TRADING_DEAL_TYPES: Final = frozenset({0, 1})

# MT5 `POSITION_TYPE_BUY` / `POSITION_TYPE_SELL`. У открытой позиции граница объявляет
# `type` перечислением, а не «неотрицательным числом», как у сделки.
POSITION_TYPES: Final = frozenset({0, 1})

MAX_SYMBOL_LENGTH: Final = 64
MAX_COMMENT_LENGTH: Final = 255
MAX_BIGINT: Final = 2**63 - 1
MONEY_LIMIT: Final = Decimal(10) ** 16
QUANTITY_LIMIT: Final = Decimal(10) ** 10

# Формат `time_server` из схемы: наивное время, секундная гранулярность.
SERVER_TIME_FORMAT: Final = "%Y-%m-%dT%H:%M:%S"


class RawDeal(Protocol):
    """Строка `mt5.history_deals_get()`. Протокол, а не класс: терминал отдаёт namedtuple."""

    ticket: int
    order: int
    time: int
    time_msc: int
    type: int
    entry: int
    magic: int
    position_id: int
    reason: int
    volume: float
    price: float
    commission: float
    swap: float
    profit: float
    fee: float
    symbol: str
    comment: str


class RawPosition(Protocol):
    """Строка `mt5.positions_get()`. `identifier` — это `position_id` в терминах контракта."""

    identifier: int
    symbol: str
    type: int
    volume: float
    price_open: float
    time: int
    sl: float
    tp: float
    profit: float


class RawAccountInfo(Protocol):
    """`mt5.account_info()` в той части, которую читает коллектор (SPEC.md 6.1).

    ⚠️ `login` и `server` в батч **не уезжают** — их там нет в контракте. Они здесь потому,
    что это ответ на вопрос «чей счёт открыт в терминале», а спрашивается он тем же самым
    вызовом, что и валюта с балансом (`X-66`). Один вызов вместо двух — не экономия: два
    вызова дали бы два снимка, и проверить можно было бы один, а отправить содержимое
    другого.
    """

    login: int
    server: str
    currency: str
    margin_mode: int
    balance: float
    equity: float


class UnsendableError(ValueError):
    """Данные, которые в контракт не переводятся. Несёт причину человеческими словами."""


class UnsendableDealError(UnsendableError):
    """Сделка, которую граница API отвергнет."""


@dataclass(frozen=True)
class Rejected:
    """Отбракованная строка терминала: чем её найти и почему она не уехала.

    `ticket` — тикет сделки или `identifier` открытой позиции: и то и другое видно в
    терминале глазами, а число без адреса не даёт человеку ничего.
    """

    ticket: int
    reason: str


# --------------------------------------------------------------------------------------
# Значения
# --------------------------------------------------------------------------------------


def decimal_text(value: float | int | Decimal) -> str:
    """Число терминала → строка без экспоненты, как требует шаблон схемы.

    `format(…, "f")` обязателен: `str(1e-07)` даёт `'1e-07'`, а шаблон схемы экспоненты
    не знает и отверг бы батч целиком.
    """
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise UnsendableDealError(f"нечисловое значение {value!r}") from error
    if not number.is_finite():
        raise UnsendableDealError(f"нечисловое значение {value!r}")
    return format(number, "f")


def server_time_text(epoch_seconds: int) -> str:
    """Секунды эпохи из терминала → наивное время сервера брокера (SPEC.md 6.3).

    `fromtimestamp(t, tz=UTC)` даёт «фальшивый UTC», равный часам брокера; именно его
    контракт называет `time_server`. Считать его настоящим UTC нельзя — на этом стоит
    весь раздел 6.3.
    """
    if epoch_seconds <= 0:
        raise UnsendableDealError(f"время сделки не задано ({epoch_seconds})")
    try:
        moment = datetime.fromtimestamp(epoch_seconds, tz=UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise UnsendableDealError(f"время сделки вне календаря ({epoch_seconds})") from error
    return moment.strftime(SERVER_TIME_FORMAT)


def margin_mode_name(code: int) -> str:
    """`ACCOUNT_MARGIN_MODE` → строка контракта. Незнакомый код — отказ, а не догадка."""
    try:
        return MARGIN_MODES[code]
    except KeyError as error:
        raise UnsendableError(f"терминал сообщил неизвестный режим счёта {code}") from error


def clean_comment(comment: str) -> str:
    """Комментарий брокера в том виде, в каком его примет схема.

    Режется ровно то, что запрещает граница (`COMMENT_PATTERN` в `schemas.py`): управляющие
    символы `\\x00–\\x1f` и `\\x7f`, плюс длина сверх 255. Ни знака больше: `\\xa0`,
    zero-width и прочая типографика брокера — его данные, а не наш мусор, и вырезать их
    значило бы молча править комментарий, который человек увидит в терминале целым.
    """
    stripped = "".join(char for char in comment if not _forbidden_in_comment(char))
    return stripped[:MAX_COMMENT_LENGTH]


def _forbidden_in_comment(char: str) -> bool:
    return char < " " or char == "\x7f"


# --------------------------------------------------------------------------------------
# Отбраковка: что граница API точно не примет
# --------------------------------------------------------------------------------------


def unsendable_reason(deal: RawDeal) -> str | None:
    """`None` — сделку можно отправлять. Строка — почему сервер её отвергнет.

    Проверяется только то, что выражено в опубликованной схеме и в валидаторах
    `app/domains/ingest/schemas.py`. Придумывать сверх этого нельзя: лишняя проверка
    выбрасывает сделку, которую сервер принял бы.
    """
    for name in ("ticket", "order", "position_id", "magic"):
        value = getattr(deal, name)
        if not isinstance(value, int) or isinstance(value, bool):
            return f"{name} не целое число"
        if value < 0 or value > MAX_BIGINT:
            return f"{name} вне диапазона bigint: {value}"
    if deal.type < 0:
        return f"тип сделки отрицательный: {deal.type}"
    if deal.reason < 0:
        return f"код причины отрицательный: {deal.reason}"
    if not 0 <= deal.entry <= 3:
        return f"entry вне диапазона 0..3: {deal.entry}"
    symbol_problem = _symbol_problem(deal)
    if symbol_problem is not None:
        return symbol_problem
    try:
        server_time = server_time_text(deal.time)
    except UnsendableDealError as error:
        return str(error)
    if deal.time_msc < 0:
        return f"time_msc отрицательный: {deal.time_msc}"
    if deal.time_msc // 1000 != deal.time:
        return f"time и time_msc расходятся: {server_time} против {deal.time_msc} мс"
    return _amounts_problem(deal)


def _symbol_problem(deal: RawDeal) -> str | None:
    symbol = deal.symbol
    if len(symbol) > MAX_SYMBOL_LENGTH:
        return f"символ длиннее {MAX_SYMBOL_LENGTH} знаков: {symbol[:16]}…"
    # Шаблон схемы — `^\S*$`: пробел внутри имени инструмента отвергает весь батч.
    if any(char.isspace() for char in symbol):
        return f"в символе пробелы: {symbol!r}"
    if symbol == "" and deal.type in TRADING_DEAL_TYPES:
        return "торговая сделка без символа"
    return None


def _amounts_problem(deal: RawDeal) -> str | None:
    for name, limit, allow_negative in (
        ("volume", QUANTITY_LIMIT, False),
        ("price", QUANTITY_LIMIT, False),
        ("profit", MONEY_LIMIT, True),
        ("commission", MONEY_LIMIT, True),
        ("swap", MONEY_LIMIT, True),
        ("fee", MONEY_LIMIT, True),
    ):
        raw = getattr(deal, name)
        try:
            text = decimal_text(raw)
        except UnsendableDealError as error:
            return f"{name}: {error}"
        number = Decimal(text)
        if not allow_negative and number < 0:
            return f"{name} отрицательный: {text}"
        if abs(number) >= limit:
            return f"{name} не помещается в колонку: {text}"
    return None


def split_sendable(deals: Iterable[RawDeal]) -> tuple[list[RawDeal], list[Rejected]]:
    """Разделить сделки на те, что уедут, и те, что сервер отверг бы вместе со всеми."""
    sendable: list[RawDeal] = []
    rejected: list[Rejected] = []
    for deal in deals:
        reason = unsendable_reason(deal)
        if reason is None:
            sendable.append(deal)
        else:
            rejected.append(Rejected(ticket=deal.ticket, reason=reason))
    return sendable, rejected


def unsendable_position_reason(position: RawPosition) -> str | None:
    """`None` — открытую позицию можно отправлять. Строка — почему сервер её отвергнет.

    Граница к открытым позициям **строже**, чем к сделкам: `type` там перечисление `0|1`,
    а не любое неотрицательное число, и символ обязан быть непустым всегда. При этом
    открытые позиции едут в каждом чанке окна, поэтому одна негодная позиция отвергала бы
    не один батч, а все до единого — счёт встал бы навсегда и не чинился бы ретраем.
    """
    identifier = position.identifier
    if not isinstance(identifier, int) or isinstance(identifier, bool):
        return "идентификатор позиции не целое число"
    if identifier < 0 or identifier > MAX_BIGINT:
        return f"идентификатор позиции вне диапазона bigint: {identifier}"
    if position.type not in POSITION_TYPES:
        return f"тип позиции не buy и не sell: {position.type}"
    symbol_problem = _position_symbol_problem(position.symbol)
    if symbol_problem is not None:
        return symbol_problem
    try:
        server_time_text(position.time)
    except UnsendableDealError as error:
        return str(error)
    return _position_amounts_problem(position)


def _position_symbol_problem(symbol: str) -> str | None:
    if symbol == "" or symbol.strip() == "":
        # `^\S+$` с `minLength: 1`: у открытой позиции инструмент есть всегда, поэтому
        # послабления для неторговых операций, которое есть у сделок, здесь нет.
        return "открытая позиция без символа"
    if len(symbol) > MAX_SYMBOL_LENGTH:
        return f"символ длиннее {MAX_SYMBOL_LENGTH} знаков: {symbol[:16]}…"
    if any(char.isspace() for char in symbol):
        return f"в символе пробелы: {symbol!r}"
    return None


def _position_amounts_problem(position: RawPosition) -> str | None:
    for name, limit, allow_negative in (
        ("volume", QUANTITY_LIMIT, False),
        ("price_open", QUANTITY_LIMIT, False),
        ("sl", QUANTITY_LIMIT, False),
        ("tp", QUANTITY_LIMIT, False),
        ("profit", MONEY_LIMIT, True),
    ):
        raw = getattr(position, name)
        try:
            text = decimal_text(raw)
        except UnsendableDealError as error:
            return f"{name}: {error}"
        number = Decimal(text)
        if not allow_negative and number < 0:
            return f"{name} отрицательный: {text}"
        if abs(number) >= limit:
            return f"{name} не помещается в колонку: {text}"
    return None


def split_sendable_positions(
    positions: Iterable[RawPosition],
) -> tuple[list[RawPosition], list[Rejected]]:
    """То же разделение для открытых позиций.

    Цена отбраковки здесь мала и названа: сборщик читает из записи `open_positions` один
    `position_id` и влияет ею только на `status`, а `status` считается ещё и по балансу
    объёмов. Открытая позиция без своей записи остаётся открытой, потому что её сделки
    не сходятся в ноль.
    """
    sendable: list[RawPosition] = []
    rejected: list[Rejected] = []
    for position in positions:
        reason = unsendable_position_reason(position)
        if reason is None:
            sendable.append(position)
        else:
            rejected.append(Rejected(ticket=position.identifier, reason=reason))
    return sendable, rejected


# --------------------------------------------------------------------------------------
# Сборка тела
# --------------------------------------------------------------------------------------


def deal_payload(deal: RawDeal) -> dict[str, Any]:
    """Одна сделка терминала в терминах контракта. Порядок ключей — как в `SPEC.md` §5.3."""
    return {
        "ticket": deal.ticket,
        "order": deal.order,
        "position_id": deal.position_id,
        "type": deal.type,
        "symbol": deal.symbol,
        "entry": deal.entry,
        "reason": deal.reason,
        "volume": decimal_text(deal.volume),
        "price": decimal_text(deal.price),
        "profit": decimal_text(deal.profit),
        "commission": decimal_text(deal.commission),
        "swap": decimal_text(deal.swap),
        "fee": decimal_text(deal.fee),
        "time_server": server_time_text(deal.time),
        "time_msc": deal.time_msc,
        "comment": clean_comment(deal.comment),
        "magic": deal.magic,
    }


def open_position_payload(position: RawPosition) -> dict[str, Any]:
    """Открытая позиция терминала в терминах контракта.

    `identifier`, а не `ticket`: у `mt5.positions_get()` идентификатор позиции лежит в
    `identifier`, а `ticket` совпадает с ним только пока позицию не переоткрывали.
    """
    return {
        "position_id": position.identifier,
        "symbol": position.symbol,
        "type": position.type,
        "volume": decimal_text(position.volume),
        "price_open": decimal_text(position.price_open),
        "time_server": server_time_text(position.time),
        "sl": decimal_text(position.sl),
        "tp": decimal_text(position.tp),
        "profit": decimal_text(position.profit),
    }


def account_info_payload(info: RawAccountInfo) -> dict[str, Any]:
    return {
        "currency": info.currency.strip().upper(),
        "margin_mode": margin_mode_name(info.margin_mode),
        "balance": decimal_text(info.balance),
        "equity": decimal_text(info.equity),
    }


def build_batch(
    *,
    account_id: str,
    server_utc_offset_minutes: int,
    account_info: RawAccountInfo,
    deals: Sequence[RawDeal],
    open_positions: Sequence[RawPosition],
) -> dict[str, Any]:
    """Тело `POST /ingest/deals` целиком."""
    return {
        "account_id": account_id,
        "source": SOURCE_COLLECTOR,
        "server_utc_offset_minutes": server_utc_offset_minutes,
        "account_info": account_info_payload(account_info),
        "deals": [deal_payload(deal) for deal in deals],
        "open_positions": [open_position_payload(item) for item in open_positions],
    }
