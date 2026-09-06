"""Формулы сводки — `docs/metrics.md`, SPEC.md 5.5.

Модуль **чистый**: ни базы, ни часов, ни окружения. Вход — уже посчитанные базой суммы и
счётчики (`Totals`), выход — числа для ответа (`Summary`). Проверяется по исходнику,
`tests/unit/test_metrics.py` (механизм — `tests/purity.py`).

**Ни одного арифметического оператора над `Decimal` здесь нет, и это не стиль.**
`decimal.getcontext()` задаёт точность и режим округления на поток, а не на модуль, и
поменять её может любой код в процессе — библиотека, чужой домен, скрипт. Тогда `a / b` и
даже `a + b` начинают считать по чужим правилам, и метрики расходятся между машинами или
после обновления зависимости, **а тесты зелёные на обеих** (найдено ревью `S1-02`,
`docs/mt5-assumptions.md`). Поэтому всё идёт через `METRICS_CONTEXT`: `divide`, `quantize`.
Оператор `/` над `Decimal` в этом файле — ошибка, даже если на этих числах он даёт тот же
ответ. Держат правило два теста: враждебный контекст снаружи не меняет ни одного числа, и
`getcontext`/`setcontext`/`localcontext` запрещены проверкой чистоты.

Второе решение, которое иначе разошлось бы молча: `None` означает «считать нечего», а не
«вышло ноль». Сумма пустого множества — честный ноль; среднее и доля пустого множества не
существуют. Ноль на их месте читается как «плохо» — особенно у `profit_factor`, где
отсутствие убытков это лучший возможный результат, а не худший. Разбор — `docs/metrics.md` §3.1.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Context, Decimal

# Точность заведомо больше, чем нужно `numeric(18,2)`: 18 значащих цифр в операнде плюс
# запас на деление до округления. Режим — «школьный», а не питоновский ROUND_HALF_EVEN:
# человек проверяет число на калькуляторе, а тот округляет половину вверх (14.625 → 14.63).
# Ловушки — по умолчанию у нового Context (InvalidOperation, DivisionByZero, Overflow):
# деление на ноль здесь всегда ошибка кода, потому что пустые множества отсеиваются выше.
METRICS_PRECISION = 38
METRICS_CONTEXT = Context(prec=METRICS_PRECISION, rounding=ROUND_HALF_UP)

MONEY_SCALE = Decimal("0.01")
# Четыре знака у доли — чтобы одна сделка из двухсот меняла winrate: шаг там 0,5 %.
RATIO_SCALE = Decimal("0.0001")
FACTOR_SCALE = Decimal("0.01")

ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class Totals:
    """Сырые итоги периода: всё, что умеет посчитать база, и ничего сверх того.

    Денежные поля — суммы `numeric(18,2)`, то есть точные. `gross_profit` и `gross_loss`
    считаются по `net_pnl` (а не по `gross_pnl`): сделка названа выигрышной по `net_pnl`,
    по нему же идёт её вклад — иначе она стояла бы в `wins`, а её деньги в знаменателе
    `profit_factor`.
    """

    trades: int
    wins: int
    losses: int
    breakeven: int
    open_positions: int
    gross_pnl: Decimal
    net_pnl: Decimal
    commission: Decimal
    swap: Decimal
    fee: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
    best_trade: Decimal | None
    worst_trade: Decimal | None


@dataclass(frozen=True, slots=True)
class Summary:
    """Ответ `GET /analytics/summary` в доменных типах — SPEC.md 5.5."""

    trades: int
    wins: int
    losses: int
    breakeven: int
    open_positions: int
    winrate: Decimal | None
    net_pnl: Decimal
    gross_pnl: Decimal
    commission: Decimal
    swap: Decimal
    fee: Decimal
    profit_factor: Decimal | None
    avg_win: Decimal | None
    avg_loss: Decimal | None
    expectancy: Decimal | None
    best_trade: Decimal | None
    worst_trade: Decimal | None


def money(value: Decimal) -> Decimal:
    """Деньги к масштабу `numeric(18,2)` явным контекстом, а не контекстом потока."""
    return value.quantize(MONEY_SCALE, context=METRICS_CONTEXT)


def ratio(numerator: Decimal, denominator: Decimal, scale: Decimal) -> Decimal:
    """Деление и округление — только через контекст модуля. Делитель обязан быть ненулевым."""
    return METRICS_CONTEXT.divide(numerator, denominator).quantize(scale, context=METRICS_CONTEXT)


def average(total: Decimal, count: int) -> Decimal | None:
    """Среднее по множеству. `None` у пустого: среднее «ни по чему» не равно нулю."""
    if count == 0:
        return None
    return ratio(total, Decimal(count), MONEY_SCALE)


def winrate(wins: int, trades: int) -> Decimal | None:
    """Доля выигрышных от **всех** закрытых сделок, включая закрытые в ноль.

    Сделка в ноль закрыта не в плюс, поэтому в числитель не идёт; но она произошла,
    поэтому идёт в знаменатель. `None` при `trades = 0` — «нечего считать», а не «0 %».
    """
    if trades == 0:
        return None
    return ratio(Decimal(wins), Decimal(trades), RATIO_SCALE)


def profit_factor(gross_profit: Decimal, gross_loss: Decimal) -> Decimal | None:
    """Прибыль на единицу убытка. `None`, когда убытков нет вовсе.

    Делить на ноль нельзя, «бесконечности» в JSON не бывает, а ноль был бы худшим
    ответом: он читается как провал, хотя описывает лучший возможный результат. Случай
    «убытков нет» отличается от «сделок нет» по полям `trades` и `losses`, которые уже
    есть в ответе, — отдельный признак для этого не нужен (`docs/metrics.md` §3.1).
    """
    if gross_loss == ZERO:
        return None
    return ratio(gross_profit, METRICS_CONTEXT.abs(gross_loss), FACTOR_SCALE)


def summarize(totals: Totals) -> Summary:
    """Сводка периода. Единственная точка, где из итогов получаются производные числа."""
    return Summary(
        trades=totals.trades,
        wins=totals.wins,
        losses=totals.losses,
        breakeven=totals.breakeven,
        open_positions=totals.open_positions,
        winrate=winrate(totals.wins, totals.trades),
        net_pnl=money(totals.net_pnl),
        gross_pnl=money(totals.gross_pnl),
        commission=money(totals.commission),
        swap=money(totals.swap),
        fee=money(totals.fee),
        profit_factor=profit_factor(totals.gross_profit, totals.gross_loss),
        avg_win=average(totals.gross_profit, totals.wins),
        avg_loss=average(totals.gross_loss, totals.losses),
        # Средний результат сделки одним делением: то же, что winrate × avg_win +
        # lossrate × avg_loss, но без округления промежуточных средних.
        expectancy=average(totals.net_pnl, totals.trades),
        best_trade=None if totals.best_trade is None else money(totals.best_trade),
        worst_trade=None if totals.worst_trade is None else money(totals.worst_trade),
    )
