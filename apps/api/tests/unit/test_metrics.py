"""Формулы сводки — S2-05. Числа берутся из `docs/metrics.md`, а не выдумываются здесь.

Так требует DoD задачи («тесты формул на ручных примерах»), и причина не в формальности:
пример в документе считается на бумаге и прочитан человеком, а число, придуманное внутри
теста, проверяет только то, что код делает то, что делает. Разошлись документ и код —
прав документ.

Главных тестов три.

`test_summary_matches_the_worked_example` — восемь позиций из §4 документа целиком, включая
сделку в ноль и `fee`. Суммы в нём складываются **тестом**, а не берутся из документа
готовыми: так проверяется и сам пример.

`test_hostile_decimal_context_does_not_change_any_number` — контекст `decimal` подменяется
снаружи на `prec=3, ROUND_DOWN`, и ни одно число сводки не меняется. Проверка не пустая:
рядом стоит утверждение, что тот же контекст **меняет** результат наивного `a / b` — то
есть враждебность контекста настоящая, а не выдуманная. Мутация подтверждена руками: с
`METRICS_CONTEXT.divide` → `/` в `metrics.ratio` этот тест краснеет (`avg_win` 54.2 вместо
54.25), с обратной правкой — зеленеет.

`test_metrics_never_reaches_for_clock_environment_or_io` — контекст потока запрещён по
исходнику: ни `getcontext`, ни `setcontext`, ни `localcontext` в модуле нет ни атрибутом,
ни импортом.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from decimal import ROUND_DOWN, Context, Decimal, getcontext, setcontext
from typing import Any

import pytest
from purity import (
    IMPURE_NAMES,
    IMPURE_SNIPPETS,
    PurityContract,
    bound_names,
    external_names,
    imported_modules,
    leaks,
    module_tree,
)

from app.domains.analytics import metrics

# Восемь закрытых позиций из `docs/metrics.md` §4: (gross_pnl, commission, swap, fee).
EXAMPLE_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("120.00", "-3.00", "-1.00", "0.00"),
    ("60.00", "-2.00", "0.00", "0.00"),
    ("40.00", "-4.00", "-2.00", "-1.00"),
    ("12.00", "-2.00", "0.00", "0.00"),
    ("-30.00", "-3.00", "-1.00", "0.00"),
    ("-50.00", "-2.00", "0.00", "0.00"),
    ("-10.00", "-4.00", "0.00", "0.00"),
    ("2.50", "-2.00", "-0.50", "0.00"),
)

# Открытые позиции того же периода: накопленная комиссия, в суммы сводки не входят.
EXAMPLE_OPEN = (Decimal("-1.20"), Decimal("-0.80"))


def _example_totals() -> metrics.Totals:
    """Итоги примера, сложенные по строкам. Складывает тест — модулю это не работа."""
    nets = [sum((Decimal(part) for part in row), Decimal(0)) for row in EXAMPLE_ROWS]
    wins = [net for net in nets if net > 0]
    losses = [net for net in nets if net < 0]
    return metrics.Totals(
        trades=len(nets),
        wins=len(wins),
        losses=len(losses),
        breakeven=len([net for net in nets if net == 0]),
        open_positions=len(EXAMPLE_OPEN),
        gross_pnl=sum((Decimal(row[0]) for row in EXAMPLE_ROWS), Decimal(0)),
        net_pnl=sum(nets, Decimal(0)),
        commission=sum((Decimal(row[1]) for row in EXAMPLE_ROWS), Decimal(0)),
        swap=sum((Decimal(row[2]) for row in EXAMPLE_ROWS), Decimal(0)),
        fee=sum((Decimal(row[3]) for row in EXAMPLE_ROWS), Decimal(0)),
        gross_profit=sum(wins, Decimal(0)),
        gross_loss=sum(losses, Decimal(0)),
        best_trade=max(nets),
        worst_trade=min(nets),
    )


EXAMPLE_TOTALS = _example_totals()

# Ожидаемая сводка — дословно из `docs/metrics.md` §4.
EXPECTED: dict[str, Any] = {
    "trades": 8,
    "wins": 4,
    "losses": 3,
    "breakeven": 1,
    "open_positions": 2,
    "winrate": Decimal("0.5000"),
    "net_pnl": Decimal("117.00"),
    "gross_pnl": Decimal("144.50"),
    "commission": Decimal("-22.00"),
    "swap": Decimal("-4.50"),
    "fee": Decimal("-1.00"),
    "profit_factor": Decimal("2.17"),
    "avg_win": Decimal("54.25"),
    "avg_loss": Decimal("-33.33"),
    "expectancy": Decimal("14.63"),
    "best_trade": Decimal("116.00"),
    "worst_trade": Decimal("-52.00"),
}


def empty_totals(**overrides: Any) -> metrics.Totals:
    """Итоги пустого периода. Тест меняет только то, что проверяет."""
    zero = Decimal("0.00")
    values: dict[str, Any] = {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "open_positions": 0,
        "gross_pnl": zero,
        "net_pnl": zero,
        "commission": zero,
        "swap": zero,
        "fee": zero,
        "gross_profit": zero,
        "gross_loss": zero,
        "best_trade": None,
        "worst_trade": None,
    }
    values.update(overrides)
    return metrics.Totals(**values)


def test_the_worked_example_adds_up_as_written() -> None:
    """Сначала проверяется сам пример: суммы строк обязаны дать строку «Σ» документа."""
    assert EXAMPLE_TOTALS.gross_pnl == Decimal("144.50")
    assert EXAMPLE_TOTALS.commission == Decimal("-22.00")
    assert EXAMPLE_TOTALS.swap == Decimal("-4.50")
    assert EXAMPLE_TOTALS.fee == Decimal("-1.00")
    assert EXAMPLE_TOTALS.net_pnl == Decimal("117.00")
    # Тождество, которое человек проверяет калькулятором первым.
    assert EXAMPLE_TOTALS.net_pnl == (
        EXAMPLE_TOTALS.gross_pnl
        + EXAMPLE_TOTALS.commission
        + EXAMPLE_TOTALS.swap
        + EXAMPLE_TOTALS.fee
    )
    assert EXAMPLE_TOTALS.trades == (
        EXAMPLE_TOTALS.wins + EXAMPLE_TOTALS.losses + EXAMPLE_TOTALS.breakeven
    )


@pytest.mark.parametrize("field", sorted(EXPECTED))
def test_summary_matches_the_worked_example(field: str) -> None:
    """Каждое поле сводки — отдельным случаем: падает одно, видно какое."""
    assert getattr(metrics.summarize(EXAMPLE_TOTALS), field) == EXPECTED[field]


def test_expectancy_agrees_with_the_classic_formula() -> None:
    """`net_pnl / trades` и `winrate × avg_win + lossrate × avg_loss` — одно число.

    Второе написание в ответ не уходит, но в документе оно есть как проверка, и если два
    определения разойдутся, узнать об этом лучше здесь, а не от человека с калькулятором.
    """
    summary = metrics.summarize(EXAMPLE_TOTALS)
    assert summary.avg_win is not None
    win_rate = Decimal(EXAMPLE_TOTALS.wins) / Decimal(EXAMPLE_TOTALS.trades)
    loss_rate = Decimal(EXAMPLE_TOTALS.losses) / Decimal(EXAMPLE_TOTALS.trades)
    exact_avg_loss = EXAMPLE_TOTALS.gross_loss / Decimal(EXAMPLE_TOTALS.losses)
    classic = win_rate * summary.avg_win + loss_rate * exact_avg_loss
    assert classic == Decimal("14.625")
    assert summary.expectancy == Decimal("14.63")


def test_rounding_is_half_up_not_bankers() -> None:
    """14.625 → 14.63. По умолчанию Python округлил бы до 14.62, и это заметит человек."""
    assert metrics.summarize(EXAMPLE_TOTALS).expectancy == Decimal("14.63")
    assert Decimal("14.625").quantize(Decimal("0.01")) == Decimal("14.62")


def test_nothing_to_count_is_not_zero() -> None:
    """Пустой период: суммы — ноль, средние и доли — `null` (`docs/metrics.md` §4.1)."""
    summary = metrics.summarize(empty_totals(open_positions=3))

    assert (summary.trades, summary.wins, summary.losses, summary.breakeven) == (0, 0, 0, 0)
    assert summary.open_positions == 3
    assert summary.net_pnl == Decimal("0.00")
    assert summary.gross_pnl == Decimal("0.00")
    assert summary.winrate is None
    assert summary.profit_factor is None
    assert summary.avg_win is None
    assert summary.avg_loss is None
    assert summary.expectancy is None
    assert summary.best_trade is None
    assert summary.worst_trade is None


def test_no_losses_leaves_profit_factor_undefined() -> None:
    """Лучший возможный результат не должен выглядеть как ноль.

    `null` при `trades > 0` и `losses = 0` читается однозначно и без отдельного признака.
    """
    summary = metrics.summarize(
        empty_totals(
            trades=2,
            wins=2,
            gross_pnl=Decimal("20.00"),
            net_pnl=Decimal("20.00"),
            gross_profit=Decimal("20.00"),
            best_trade=Decimal("12.00"),
            worst_trade=Decimal("8.00"),
        )
    )

    assert summary.profit_factor is None
    assert summary.losses == 0
    assert summary.trades == 2
    assert summary.avg_loss is None
    assert summary.avg_win == Decimal("10.00")
    assert summary.winrate == Decimal("1.0000")


def test_no_wins_gives_profit_factor_zero() -> None:
    """А вот здесь ноль честен: прибыли нет, убыток есть."""
    summary = metrics.summarize(
        empty_totals(
            trades=2,
            losses=2,
            gross_pnl=Decimal("-20.00"),
            net_pnl=Decimal("-20.00"),
            gross_loss=Decimal("-20.00"),
            best_trade=Decimal("-8.00"),
            worst_trade=Decimal("-12.00"),
        )
    )

    assert summary.profit_factor == Decimal("0.00")
    assert summary.winrate == Decimal("0.0000")
    assert summary.avg_win is None
    assert summary.avg_loss == Decimal("-10.00")


def test_only_breakeven_trades() -> None:
    """`trades` есть, а победителей и проигравших нет: доля 0, множитель не определён."""
    summary = metrics.summarize(
        empty_totals(trades=3, breakeven=3, best_trade=Decimal("0.00"), worst_trade=Decimal("0.00"))
    )

    assert summary.winrate == Decimal("0.0000")
    assert summary.profit_factor is None
    assert summary.expectancy == Decimal("0.00")


def test_average_loss_keeps_the_broker_sign() -> None:
    """Средний убыток отрицателен — иначе в одном ответе два соглашения о знаке."""
    summary = metrics.summarize(EXAMPLE_TOTALS)
    assert summary.avg_loss is not None
    assert summary.avg_loss < 0
    assert summary.worst_trade is not None
    assert summary.worst_trade < 0


def test_winrate_counts_breakeven_in_the_denominator() -> None:
    """Сделка в ноль закрыта не в плюс, но она произошла: 1 из 2, а не 1 из 1."""
    assert metrics.winrate(wins=1, trades=2) == Decimal("0.5000")
    assert metrics.winrate(wins=0, trades=0) is None


def test_winrate_keeps_four_decimals() -> None:
    """Двух знаков не хватает: одна сделка из двухсот меняет долю на 0,5 %."""
    assert metrics.winrate(wins=3, trades=7) == Decimal("0.4286")
    assert metrics.winrate(wins=100, trades=200) != metrics.winrate(wins=101, trades=200)


# --- контекст decimal (развилка 1 тикета, `docs/metrics.md` §3.3) ---------------


@pytest.fixture
def hostile_decimal_context() -> Iterator[None]:
    """Чужой контекст в потоке: три значащих цифры и округление вниз.

    Ровно то, что может сделать посторонняя библиотека или скрипт. Восстанавливается
    обязательно — иначе тест утёк бы в соседние и сделал бы их красными по своей вине.
    """
    original = getcontext()
    setcontext(Context(prec=3, rounding=ROUND_DOWN))
    yield
    setcontext(original)


def test_the_hostile_context_really_is_hostile(hostile_decimal_context: None) -> None:
    """Проверка проверки: без явного контекста те же числа считаются иначе.

    Без этого утверждения тест ниже был бы зелёным и на модуле, который ничего не защищает.
    """
    assert Decimal("217.00") / Decimal("4") != Decimal("54.25")
    assert Decimal("1234.56") + Decimal("1.00") != Decimal("1235.56")


def test_hostile_decimal_context_does_not_change_any_number(
    hostile_decimal_context: None,
) -> None:
    """Метрики не зависят от того, что посторонний код сделал с контекстом потока."""
    summary = metrics.summarize(EXAMPLE_TOTALS)

    for field, expected in EXPECTED.items():
        assert getattr(summary, field) == expected, field


# --- чистота модуля ------------------------------------------------------------

METRICS_PURITY = PurityContract(
    allowed_imports=frozenset({"__future__", "dataclasses", "decimal"}),
    allowed_builtins=frozenset({"int"}),
)


def test_metrics_imports_nothing_impure() -> None:
    assert imported_modules(module_tree(metrics)) <= METRICS_PURITY.allowed_imports


def test_metrics_takes_nothing_from_outside_beyond_imports_and_plain_builtins() -> None:
    tree = module_tree(metrics)
    assert [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)], (
        "модуль обязан определять функции, иначе тест ничего не проверяет"
    )
    assert external_names(tree) <= METRICS_PURITY.allowed_builtins


def test_metrics_never_reaches_for_clock_environment_or_io() -> None:
    tree = module_tree(metrics)
    assert leaks(tree, METRICS_PURITY) == set()
    # Иначе дыру можно открыть, дописав `getcontext` в белый список, и оба теста
    # останутся зелёными.
    assert METRICS_PURITY.allowed_builtins.isdisjoint(IMPURE_NAMES)
    assert bound_names(tree).isdisjoint(METRICS_PURITY.guarded), (
        "модуль затеняет имя, на котором держится проверка"
    )


def test_importing_the_thread_context_by_name_is_caught() -> None:
    """`from decimal import getcontext` мимо `leaks` проходит — его ловит `guarded`.

    Две формы обращения к контексту закрываются двумя разными проверками, и проверить
    надо обе: атрибутную ловит `leaks` (случай `decimal_context_from_thread` ниже),
    импортную — вот эта.
    """
    imported = ast.parse("from decimal import getcontext\nX = getcontext().prec\n")
    assert not bound_names(imported).isdisjoint(METRICS_PURITY.guarded)


@pytest.mark.parametrize("case", sorted(IMPURE_SNIPPETS))
def test_purity_check_is_not_vacuous(case: str) -> None:
    """Известные обходы обязаны быть красными и на этом контракте."""
    assert leaks(ast.parse(IMPURE_SNIPPETS[case]), METRICS_PURITY)
