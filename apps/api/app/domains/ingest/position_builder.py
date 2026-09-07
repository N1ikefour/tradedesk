"""Сборка позиции журнала из сделок брокера (S1-03, SPEC.md 7).

Позиция — единица журнала, и она не приходит от брокера: MT5 отдаёт только сделки.
Здесь из них получается строка `positions`, и это последнее место, где ошибка ещё
дешёвая: дальше на `positions.id` повиснут заметки, теги и рефлексии пользователя.

Функция чистая: ни БД, ни «сейчас», ни зоны машины, ни контекста `decimal` из потока.
Причина та же, что у нормализатора, — неверная сборка не падает, она молча пишет не то
число, и находится это в сверке с отчётом терминала недели спустя (S1-12). Единственная
защита — воспроизводимость: одни и те же сделки обязаны давать одну и ту же строку на
любой машине. Контракт чистоты проверяет `tests/unit/test_position_builder.py`.

Чего здесь намеренно нет:

- **записи в БД** — S1-04. Отсюда выходит `BuiltPosition`, а не строка целиком: `id`,
  `account_id`, `symbol_norm` (S1-07), `is_manual` и `rebuilt_at` сделками не
  определяются, их проставляет тот, кто пишет;
- **разбора комментария брокера.** `PositionDeal` его не объявляет, и это не экономия:
  у брокера из первой выгрузки признак стопа живёт только в тексте (`LimitSell[sl]`),
  а `reason` у таких сделок равен 0 (клиент). SPEC.md 7 велит брать `close_reason` из
  `reason`, и код берёт из `reason`. Читать вместо этого комментарий — смена правила
  спеки, то есть отдельное решение, а не догадка сборщика;
- **плавающей прибыли открытой позиции** — см. `OpenPositionSnapshot`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Context, Decimal
from typing import Literal, Protocol

from app.domains.ingest.normalizer import DealType, Entry, Reason, deal_role
from app.domains.ingest.schemas import IngestOpenPosition

Direction = Literal["long", "short"]
PositionStatus = Literal["open", "closed"]

# Арифметика идёт явным контекстом, а не операторами: точность и режим округления
# `Decimal` лежат в контексте потока, и поменять их может любой код в процессе. Урок
# S2-05 (`docs/metrics.md` §3.3) — там зависимость от чужого контекста доказана мутацией.
POSITION_CONTEXT = Context(prec=38, rounding=ROUND_HALF_UP)

# Масштабы колонок SPEC.md 3.3: деньги — numeric(18,2), цены и объёмы — numeric(18,8).
MONEY_EXPONENT = Decimal("0.01")
QUANTITY_EXPONENT = Decimal("0.00000001")

# SPEC.md 7: позиция закрыта, когда |opened − closed| меньше этого. Объёмы к моменту
# сравнения уже квантованы до 1e-8, поэтому условие означает «ровно поровну» — и это
# намеренно: «почти закрыта» не должно зависеть от того, как легли последние знаки.
VOLUME_TOLERANCE = Decimal("1e-8")

NO_DEALS = "Позиция собирается минимум из одной сделки"
MIXED_POSITIONS = "Сделки принадлежат разным позициям"
FOREIGN_OPEN_POSITION = "Запись open_positions относится к другой позиции"
NON_POSITION_DEAL = "Сделка не участвует в сборке позиций (SPEC.md 6.2)"
NO_ENTRY_VOLUME = "У позиции нет ни одного входа: собирать нечего"


class PositionBuildError(ValueError):
    """Сделки не складываются в позицию. Что с этим делать — решает вызывающий (S1-04)."""


class PositionDeal(Protocol):
    """Сделка позиции — ровно те поля, которые читает алгоритм SPEC.md 7.

    Протокол, а не конкретный класс, потому что читателей у одной позиции двое и приходят
    они разными путями: `NormalizedDeal` — сделки текущего батча, строка `deals` — те,
    что приехали батчами прошлыми. Оба вида подходят структурно, второго прочтения
    данных ради этого заводить не нужно.

    Перечень полей закрытый, и это его главная работа: `comment` и `raw` в нём
    отсутствуют, поэтому сборщик физически не может подсмотреть в них признак стопа
    мимо `reason` (см. модульную строку). Поля только на чтение — сборщик ничего в
    сделке не меняет: `deals` append-only.
    """

    @property
    def deal_ticket(self) -> int: ...

    @property
    def position_id(self) -> int: ...

    @property
    def symbol_raw(self) -> str: ...

    @property
    def deal_type(self) -> DealType: ...

    @property
    def entry(self) -> Entry: ...

    @property
    def reason(self) -> Reason: ...

    @property
    def volume(self) -> Decimal: ...

    @property
    def price(self) -> Decimal: ...

    @property
    def profit(self) -> Decimal: ...

    @property
    def commission(self) -> Decimal: ...

    @property
    def swap(self) -> Decimal: ...

    @property
    def fee(self) -> Decimal: ...

    @property
    def time_utc(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class OpenPositionSnapshot:
    """Запись `open_positions` из батча в том объёме, в каком её вправе читать сборщик.

    Поле ровно одно, и `profit` среди них нет намеренно. `positions_get()` отдаёт
    плавающий результат открытой позиции, и записать его в `net_pnl` — соблазн, у
    которого уже есть цена: на утверждении «у открытой позиции в `net_pnl` накопленные
    издержки, а не плавающий результат» построена вся сводка `S2-05`, включая объяснение
    расхождения шапки журнала с колонкой. Плавающее число сделало бы это расхождение
    величиной, меняющейся от котировки к котировке.

    SPEC.md 7 того же мнения: `gross_pnl = Σ profit по deals`. У открытой позиции сделок
    выхода ещё нет, у сделки входа `profit = 0`, значит в `net_pnl` остаются комиссия и
    своп — ровно накопленные издержки. Запись открытой позиции влияет **только** на
    `status`, и урезанный снимок делает это не обещанием, а свойством типа.
    """

    position_id: int


@dataclass(frozen=True, slots=True)
class BuiltPosition:
    """Строка `positions` в той части, которую определяют сделки (SPEC.md 3.3).

    Остального здесь нет, потому что оно не выводится из сделок и проставляется при
    записи (S1-04): `id` (переживает UPSERT, на нём висит пользовательский слой),
    `account_id`, `symbol_norm` (S1-07), `is_manual` и `rebuilt_at`.
    """

    position_id: int
    symbol_raw: str
    direction: Direction
    status: PositionStatus
    open_time: datetime
    close_time: datetime | None
    volume_opened: Decimal
    volume_closed: Decimal
    avg_entry_price: Decimal
    avg_exit_price: Decimal | None
    gross_pnl: Decimal
    commission: Decimal
    swap: Decimal
    fee: Decimal
    net_pnl: Decimal
    deals_count: int
    duration_seconds: int | None
    close_reason: Reason | None


def quantize_money(value: Decimal) -> Decimal:
    """Деньги к масштабу колонки: два знака, половина — от нуля.

    Округление живёт здесь, до сложения, а не после него, и это несущее решение. Брокер
    присылает деньги с шумом float64 (`-1.6099999999999999` — это `-1.61`, выгрузка
    7 сентября 2026), а `deals.profit` — numeric(18,2), то есть в БД каждая сделка ляжет
    округлённой. Сложи сборщик сырые значения и округли сумму — позиция разошлась бы с
    суммой собственных сделок на копейки, а S1-12 требует сойтись с отчётом терминала
    в 0,00.

    ROUND_HALF_UP в Python — «половина от нуля», ровно так же приводит к numeric и
    Postgres. Поэтому сумма позиции совпадает с суммой сохранённых сделок независимо от
    того, округлит ли их S1-04 явно.
    """
    return value.quantize(MONEY_EXPONENT, context=POSITION_CONTEXT)


def quantize_quantity(value: Decimal) -> Decimal:
    """Объёмы и цены к масштабу колонки: восемь знаков, половина — от нуля."""
    return value.quantize(QUANTITY_EXPONENT, context=POSITION_CONTEXT)


def open_position_snapshot(record: IngestOpenPosition) -> OpenPositionSnapshot:
    """Единственный переход от записи батча к снимку — и место, где отсекается `profit`."""
    return OpenPositionSnapshot(position_id=record.position_id)


def group_position_deals(deals: Iterable[PositionDeal]) -> Mapping[int, tuple[PositionDeal, ...]]:
    """Сделки по позициям: ключ — `position_id`, значение отсортировано как требует §7.

    Неторговые операции (`balance`, `credit`, `other` с нулевым `position_id`) отсеяны по
    §6.2 — правило берётся у нормализатора, второй копии здесь нет.

    Группа с `position_id = 0` не выбрасывается. У неторговых операций ноль как раз и
    означает «позиции нет», но их тут уже нет, а торговая сделка с нулём — случай, про
    который §6.2 молчит; в выгрузке 7 сентября 2026 все 503 торговые сделки несут
    позицию. Отбросить её значило бы завести правило, которого в спеке нет, и потерять
    сделку из журнала молча.
    """
    grouped: dict[int, list[PositionDeal]] = {}
    for deal in deals:
        if deal_role(deal.deal_type, deal.position_id) == "excluded":
            continue
        grouped.setdefault(deal.position_id, []).append(deal)
    return {position_id: _ordered(items) for position_id, items in sorted(grouped.items())}


def build_position(
    deals: Sequence[PositionDeal],
    *,
    open_position: OpenPositionSnapshot | None = None,
) -> BuiltPosition:
    """Все сделки одной позиции — в одну строку `positions` (SPEC.md 7).

    Порядок входа здесь же и восстанавливается, хотя §7 обещает его от вызывающего:
    идемпотентность пересборки не должна зависеть от того, каким `ORDER BY` сделки
    достали из базы.
    """
    ordered = _ordered(deals)
    if not ordered:
        raise PositionBuildError(NO_DEALS)

    position_id = ordered[0].position_id
    if any(deal.position_id != position_id for deal in ordered):
        raise PositionBuildError(MIXED_POSITIONS)
    if open_position is not None and open_position.position_id != position_id:
        raise PositionBuildError(FOREIGN_OPEN_POSITION)

    direction: Direction | None = None
    # Инструмент берётся у сделки входа, а не у первой в группе: корректировка `other`
    # тоже несёт `symbol`, и своим временем она может оказаться раньше входа.
    symbol_raw: str | None = None
    open_time: datetime | None = None
    close_time: datetime | None = None
    close_reason: Reason | None = None
    opened = Decimal(0)
    closed = Decimal(0)
    entry_weight = Decimal(0)
    exit_weight = Decimal(0)
    deals_count = 0

    for deal in ordered:
        role = deal_role(deal.deal_type, deal.position_id)
        if role == "excluded":
            raise PositionBuildError(NON_POSITION_DEAL)
        if role == "adjustment":
            # Корректировка приносит только деньги: ни объёма, ни цены, ни направления
            # у неё нет (SPEC.md 6.2, последний абзац). В `deals_count` она тоже не
            # входит — §7 считает торговые сделки.
            continue

        deals_count += 1
        volume = quantize_quantity(deal.volume)
        price = quantize_quantity(deal.price)

        if deal.entry == "in":
            if direction is None:
                direction = _direction(deal.deal_type)
                symbol_raw = deal.symbol_raw
                open_time = deal.time_utc
            opened = POSITION_CONTEXT.add(opened, volume)
            entry_weight = POSITION_CONTEXT.add(
                entry_weight, POSITION_CONTEXT.multiply(price, volume)
            )
        elif deal.entry == "inout":
            # Переворот на неттинге. §7 для v1: закрывается открытая часть P, остаток
            # V−P новой позиции здесь НЕ создаёт — MT5 при перевороте назначает ей свой
            # `position_id`, и она приедет своими сделками.
            if direction is None:
                direction = _direction(deal.deal_type)
                symbol_raw = deal.symbol_raw
                open_time = deal.time_utc
            closing = min(volume, POSITION_CONTEXT.subtract(opened, closed))
            if closing > 0:
                closed = POSITION_CONTEXT.add(closed, closing)
                exit_weight = POSITION_CONTEXT.add(
                    exit_weight, POSITION_CONTEXT.multiply(price, closing)
                )
                close_time = deal.time_utc
        else:
            closed = POSITION_CONTEXT.add(closed, volume)
            exit_weight = POSITION_CONTEXT.add(
                exit_weight, POSITION_CONTEXT.multiply(price, volume)
            )
            close_time = deal.time_utc
            # §7 перечисляет для `close_reason` ровно `out` и `out_by`: `inout` сюда не
            # входит, поэтому закрытая переворотом позиция остаётся без причины закрытия.
            close_reason = deal.reason

    if direction is None or symbol_raw is None or open_time is None or opened <= 0:
        raise PositionBuildError(NO_ENTRY_VOLUME)

    balanced = POSITION_CONTEXT.subtract(opened, closed).copy_abs() < VOLUME_TOLERANCE
    status: PositionStatus = "closed" if balanced and open_position is None else "open"
    if status == "open":
        close_time = None

    gross_pnl = _total(quantize_money(deal.profit) for deal in ordered)
    commission = _total(quantize_money(deal.commission) for deal in ordered)
    swap = _total(quantize_money(deal.swap) for deal in ordered)
    fee = _total(quantize_money(deal.fee) for deal in ordered)

    return BuiltPosition(
        position_id=position_id,
        symbol_raw=symbol_raw,
        direction=direction,
        status=status,
        open_time=open_time,
        close_time=close_time,
        # Квантование повторяется здесь ради позиции без единого выхода: там `closed`
        # так и остался нулём без масштаба, а колонка — numeric(18,8).
        volume_opened=quantize_quantity(opened),
        volume_closed=quantize_quantity(closed),
        avg_entry_price=quantize_quantity(POSITION_CONTEXT.divide(entry_weight, opened)),
        avg_exit_price=(
            quantize_quantity(POSITION_CONTEXT.divide(exit_weight, closed)) if closed > 0 else None
        ),
        gross_pnl=gross_pnl,
        commission=commission,
        swap=swap,
        fee=fee,
        net_pnl=_total((gross_pnl, commission, swap, fee)),
        deals_count=deals_count,
        duration_seconds=(
            int((close_time - open_time).total_seconds()) if close_time is not None else None
        ),
        # Без оглядки на `status`: §7 ставит условие «при status=closed» только у
        # `close_time`, у причины закрытия его нет. Частично закрытая позиция остаётся
        # открытой и несёт причину последнего частичного выхода.
        close_reason=close_reason,
    )


def _ordered(deals: Iterable[PositionDeal]) -> tuple[PositionDeal, ...]:
    return tuple(sorted(deals, key=lambda deal: (deal.time_utc, deal.deal_ticket)))


def _direction(deal_type: DealType) -> Direction:
    return "long" if deal_type == "buy" else "short"


def _total(values: Iterable[Decimal]) -> Decimal:
    total = Decimal(0)
    for value in values:
        total = POSITION_CONTEXT.add(total, value)
    return quantize_money(total)
