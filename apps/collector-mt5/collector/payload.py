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
3. **Сделку, которую сервер точно отвергнет, коллектор не отправляет.** `extra="forbid"`
   и валидаторы границы работают на весь батч разом: одна сделка с пробелом в символе
   означает `400` на все 5000 и остановку синхронизации счёта навсегда, без ретрая.
   Названная потеря одной сделки дешевле молчаливой остановки счёта — но она **обязана**
   быть названной, поэтому отбракованные попадают и в лог, и в heartbeat.
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
    """`mt5.account_info()` в той части, которая уезжает в батч (SPEC.md 6.1)."""

    currency: str
    margin_mode: int
    balance: float
    equity: float


class UnsendableDealError(ValueError):
    """Сделка, которую граница API отвергнет. Несёт причину человеческими словами."""


@dataclass(frozen=True)
class Rejected:
    """Отбракованная сделка: тикет для поиска в терминале и причина для человека."""

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
        raise ValueError(f"неизвестный режим счёта MT5: {code}") from error


def clean_comment(comment: str) -> str:
    """Комментарий брокера в том виде, в каком его примет схема.

    Управляющие символы вырезаются, длина режется: это ремонт формы, а не смысла, и
    альтернатива ему — `400` на весь батч из-за одного байта, который никто не читает.
    """
    stripped = "".join(char for char in comment if char.isprintable() or char == " ")
    return stripped[:MAX_COMMENT_LENGTH]


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
