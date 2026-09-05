"""Смысл числовых полей MT5: перечисления и время сервера брокера (SPEC.md 6.2–6.3).

`schemas.py` (S1-01) зафиксировал **форму** батча: `entry` уже 0..3, `time_server` уже
наивный, деньги уже `Decimal`. Здесь форма получает **значение** — коды превращаются в
доменные строки колонок `deals`, а время сервера в настоящий UTC.

Всё здесь — чистые функции: ни БД, ни «сейчас», ни переменных окружения, ни зоны машины.
Это не стилевое требование. Неверный маппинг не падает — он молча пишет не то, и найдётся
через недели в сверке (S1-12). Единственное, что от этого защищает, — воспроизводимость:
одни и те же аргументы обязаны давать один и тот же ответ на любой машине.

Чистота остаётся требованием, а не доказанным свойством: `tests/unit/test_normalizer.py`
проверяет четыре конкретные вещи — белый список импортов, белый список имён, которые
модуль берёт снаружи, отсутствие обращений к часам и окружению по имени атрибута и
совпадение результата под четырьмя `TZ`. Обход, не попавший ни в одну из четырёх, тест
пропустит; тем же файлом проверено, что три известных обхода он ловит.

Чего здесь намеренно нет: нормализации символов (S1-07, символ проходит как есть), сборки
позиций (S1-03) и записи в БД (S1-04).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from app.domains.ingest.schemas import IngestDeal, IngestDealsBatch

DealType = Literal["buy", "sell", "balance", "credit", "other"]
Entry = Literal["in", "out", "inout", "out_by"]
Reason = Literal["client", "mobile", "web", "expert", "sl", "tp", "so", "other"]

# Роль сделки в сборке позиции (SPEC.md 6.2, последний абзац). Три значения, а не два,
# потому что «участвует» распадается надвое: торговая сделка приносит объём, цену и
# направление, а корректировка — только деньги.
DealRole = Literal["trade", "adjustment", "excluded"]

UnknownCodeField = Literal["deal_type", "reason"]

SERVER_TIME_NOT_NAIVE = "Время сервера брокера обязано быть наивным (SPEC.md 6.3)"

# Таблица SPEC.md 6.2, дословно и целиком. Всё, чего здесь нет, — 'other'.
DEAL_TYPE_BY_CODE: Mapping[int, DealType] = {
    0: "buy",  # DEAL_TYPE_BUY
    1: "sell",  # DEAL_TYPE_SELL
    2: "balance",  # DEAL_TYPE_BALANCE
    3: "credit",  # DEAL_TYPE_CREDIT
}

# Запаса «прочее» у entry нет: SPEC.md 6.2 не даёт для него значения по умолчанию, а
# `deals.entry` — NOT NULL. Граница (S1-01) ограничила поле 0..3, поэтому здесь именно
# индексация, а не `.get(code, ...)`: fallback был бы недостижимой веткой, которая
# выглядит как защита. KeyError означает «сломана граница», а не «брокер прислал странное».
ENTRY_BY_CODE: Mapping[int, Entry] = {
    0: "in",  # DEAL_ENTRY_IN
    1: "out",  # DEAL_ENTRY_OUT
    2: "inout",  # DEAL_ENTRY_INOUT
    3: "out_by",  # DEAL_ENTRY_OUT_BY
}

REASON_BY_CODE: Mapping[int, Reason] = {
    0: "client",  # DEAL_REASON_CLIENT
    1: "mobile",  # DEAL_REASON_MOBILE
    2: "web",  # DEAL_REASON_WEB
    3: "expert",  # DEAL_REASON_EXPERT
    4: "sl",  # DEAL_REASON_SL
    5: "tp",  # DEAL_REASON_TP
    6: "so",  # DEAL_REASON_SO
}

# Коды, которые MT5 документирует и которые SPEC.md 6.2 осознанно сворачивает в 'other'.
# Нужны не для маппинга (`.get` и так вернёт 'other'), а чтобы отличить рутину от сигнала:
# начисление свопа приходит каждый день, и репортить его как неизвестное — утопить сигнал
# в шуме. Код вне обоих наборов означает либо новую версию терминала, либо что мы читаем
# не то перечисление, — и вот про него стоит узнать.
DOCUMENTED_OTHER_DEAL_TYPE_CODES = frozenset(
    {
        4,  # CHARGE
        5,  # CORRECTION
        6,  # BONUS
        7,  # COMMISSION
        8,  # COMMISSION_DAILY
        9,  # COMMISSION_MONTHLY
        10,  # COMMISSION_AGENT_DAILY
        11,  # COMMISSION_AGENT_MONTHLY
        12,  # INTEREST
        13,  # BUY_CANCELED
        14,  # SELL_CANCELED
        15,  # DIVIDEND
        16,  # DIVIDEND_FRANKED
        17,  # TAX
    }
)

DOCUMENTED_OTHER_REASON_CODES = frozenset(
    {
        7,  # ROLLOVER
        8,  # VMARGIN
        9,  # SPLIT
        10,  # CORPORATE_ACTION
    }
)


@dataclass(frozen=True, slots=True)
class NormalizedDeal:
    """Одна сделка в терминах колонок `deals` (SPEC.md 3.3).

    Нет полей, которые принадлежат не сделке, а батчу или счёту: `account_id`, `source`,
    `ingested_at` проставляет S1-04. Нет `symbol_norm` — это S1-07.
    """

    deal_ticket: int
    order_ticket: int
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
    time_server: datetime
    comment: str
    magic: int
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class UnknownCode:
    """Сколько раз в батче встретился код, которого нет ни в маппинге, ни в перечислении."""

    field: UnknownCodeField
    code: int
    count: int


@dataclass(frozen=True, slots=True)
class NormalizedBatch:
    deals: tuple[NormalizedDeal, ...]
    # Не ошибка: батч с неизвестными кодами принимается целиком, коды свёрнуты в 'other',
    # исходные числа лежат в `raw` каждой сделки. Этот список — то, что делает молчание
    # слышимым: S1-04 пишет его в лог одной строкой на батч, а не на сделку.
    unknown_codes: tuple[UnknownCode, ...]


def normalize_deal_type(code: int) -> DealType:
    return DEAL_TYPE_BY_CODE.get(code, "other")


def normalize_entry(code: int) -> Entry:
    """Код вне 0..3 — сломанная граница S1-01; KeyError здесь честнее тихой подмены."""
    return ENTRY_BY_CODE[code]


def normalize_reason(code: int) -> Reason:
    return REASON_BY_CODE.get(code, "other")


def deal_role(deal_type: DealType, position_id: int) -> DealRole:
    """Участвует ли сделка в сборке позиции и как (SPEC.md 6.2, последний абзац).

    Знание живёт здесь, а не в сборщике, потому что правило сформулировано в §6.2 и
    зависит ровно от двух полей. Но живёт **функцией**, а не флагом в `NormalizedDeal` и
    не колонкой: сборщик (S1-03) получает на вход строки из БД — все сделки позиции,
    включая приехавшие прошлыми батчами, — а не результат нормализации текущего батча.
    Флаг на DTO был бы ему недоступен, и он завёл бы вторую копию правила.
    """
    if deal_type in ("buy", "sell"):
        return "trade"
    # balance и credit исключены при любом position_id: так написано в §6.2. На практике
    # у них position_id = 0, но правило не про практику, а про то, что нельзя приписать
    # позиции пополнение счёта, даже если брокер проставил ей номер.
    if deal_type == "other" and position_id != 0:
        return "adjustment"
    return "excluded"


def to_utc(time_server: datetime, server_utc_offset_minutes: int) -> datetime:
    """`time_utc = time_server − offset` (SPEC.md 6.3).

    Смещение — аргумент, а не состояние счёта. Поэтому смена смещения (DST) ничего не
    пересчитывает задним числом: прошлые сделки уже переведены тем смещением, с которым
    приехали, и функции неоткуда взять «текущее».

    `.replace(tzinfo=UTC)`, а не `.astimezone(UTC)`: второй для наивного времени спросил бы
    зону машины, и результат зависел бы от того, где запущен процесс. Aware-вход отвергается,
    потому что `.replace` на нём молча переклеил бы метку зоны, оставив стрелки на месте.
    """
    if time_server.tzinfo is not None:
        raise ValueError(SERVER_TIME_NOT_NAIVE)
    return time_server.replace(tzinfo=UTC) - timedelta(minutes=server_utc_offset_minutes)


def label_server_time(time_server: datetime) -> datetime:
    """Время сервера брокера для колонки `deals.time_server` (`timestamptz`).

    Метка UTC проставляется, стрелки не двигаются: это тот самый «фальшивый UTC» из
    SPEC.md 6.3 — часы брокера, а не момент времени. Колонка типизирована `timestamptz`,
    поэтому метка нужна: без неё зону подставил бы драйвер или сессия Postgres, и значение
    «как пришло от терминала» перестало бы читаться обратно как пришло.
    """
    if time_server.tzinfo is not None:
        raise ValueError(SERVER_TIME_NOT_NAIVE)
    return time_server.replace(tzinfo=UTC)


def normalize_deal(deal: IngestDeal, server_utc_offset_minutes: int) -> NormalizedDeal:
    """Сделка батча в строку `deals`. Символ проходит как есть — нормализация в S1-07.

    `order` и `magic` переносятся как есть, включая 0: колонки nullable, но 0 — это то,
    что сказал брокер, а превращение его в NULL было бы вторым прочтением данных, которого
    SPEC.md не просит.
    """
    return NormalizedDeal(
        deal_ticket=deal.ticket,
        order_ticket=deal.order,
        position_id=deal.position_id,
        symbol_raw=deal.symbol,
        deal_type=normalize_deal_type(deal.type),
        entry=normalize_entry(deal.entry),
        reason=normalize_reason(deal.reason),
        volume=deal.volume,
        price=deal.price,
        profit=deal.profit,
        commission=deal.commission,
        swap=deal.swap,
        fee=deal.fee,
        time_utc=to_utc(deal.time_server, server_utc_offset_minutes),
        time_server=label_server_time(deal.time_server),
        comment=deal.comment,
        magic=deal.magic,
        # `deals.raw` — единственное место, где исходные числа `type`/`entry`/`reason`
        # переживают нормализацию. Это разобранная сделка, а не байты запроса, но
        # `extra="forbid"` на границе гарантирует, что выкинуть было нечего.
        # mode="json": Decimal уходит строкой, наивное время — ISO без зоны, то есть
        # JSONB получает значения без потери точности и без float.
        raw=deal.model_dump(mode="json"),
    )


def normalize_batch(batch: IngestDealsBatch) -> NormalizedBatch:
    """Весь батч. Смещение берётся из самого батча — см. `to_utc`."""
    return NormalizedBatch(
        deals=tuple(normalize_deal(deal, batch.server_utc_offset_minutes) for deal in batch.deals),
        unknown_codes=_unknown_codes(batch.deals),
    )


def _unknown_codes(deals: Sequence[IngestDeal]) -> tuple[UnknownCode, ...]:
    counts: Counter[tuple[UnknownCodeField, int]] = Counter()
    for deal in deals:
        if deal.type not in DEAL_TYPE_BY_CODE and deal.type not in DOCUMENTED_OTHER_DEAL_TYPE_CODES:
            counts[("deal_type", deal.type)] += 1
        if deal.reason not in REASON_BY_CODE and deal.reason not in DOCUMENTED_OTHER_REASON_CODES:
            counts[("reason", deal.reason)] += 1
    # Порядок детерминирован: строка в логе не должна плясать от батча к батчу.
    return tuple(
        UnknownCode(field=field, code=code, count=count)
        for (field, code), count in sorted(counts.items())
    )
