"""Имя инструмента из символа брокера: SPEC.md 6.4 и DoD S1-07.

Проверяется не «функция работает», а три конкретных способа тихо испортить журнал:

* суффикс не срезан — один инструмент разъезжается на два, и фильтр собирает не всё;
* срезано лишнее — `US30`, `US100` и `US500` складываются в один `US`, то есть три разных
  индекса сливаются в одну строку, и цифры в ней уже ничьи;
* очистка съела имя целиком — инструмент теряет имя, а `symbols.norm` NOT NULL.

Ни один из трёх не падает в рантайме, поэтому каждый закреплён примерами, а не рассуждением.
"""

from __future__ import annotations

import ast
from itertools import combinations

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

from app.domains.ingest import symbols
from app.domains.ingest.symbols import (
    KNOWN_SYMBOLS,
    UNKNOWN_ASSET_CLASS,
    clean_symbol,
    resolve_symbol,
)

# --- суффиксы: DoD требует 30 примеров -----------------------------------------------

# Каждая альтернатива регулярного выражения SPEC.md 6.4 встречается хотя бы раз, и каждый
# из трёх разделителей — тоже. Ниже отдельным тестом проверено, что примеров не меньше 30:
# иначе таблицу можно было бы незаметно ужать до трёх строк, и DoD остался бы «выполненным».
SUFFIX_CASES: tuple[tuple[str, str], ...] = (
    # `m` — три разделителя подряд, дальше по одному на альтернативу.
    ("EURUSD.m", "EURUSD"),
    ("EURUSD_m", "EURUSD"),
    ("EURUSD-m", "EURUSD"),
    ("EURUSD.micro", "EURUSD"),
    ("GBPUSD_micro", "GBPUSD"),
    ("EURUSD.mini", "EURUSD"),
    ("USDJPY-mini", "USDJPY"),
    ("EURUSD.c", "EURUSD"),
    ("USDCHF_c", "USDCHF"),
    ("EURUSD.cent", "EURUSD"),
    ("GBPUSD-cent", "GBPUSD"),
    ("EURUSD.pro", "EURUSD"),
    ("AUDUSD_pro", "AUDUSD"),
    ("EURUSD.ecn", "EURUSD"),
    ("NZDUSD-ecn", "NZDUSD"),
    ("EURUSD.raw", "EURUSD"),
    ("USDCAD_raw", "USDCAD"),
    ("EURUSD.std", "EURUSD"),
    ("XAUUSD-std", "XAUUSD"),
    ("EURUSD_i", "EURUSD"),
    ("XAGUSD.i", "XAGUSD"),
    ("EURUSD.+", "EURUSD"),
    ("EURUSD_+", "EURUSD"),
    ("EURUSD.#", "EURUSD"),
    ("EURUSD-#", "EURUSD"),
    ("EURUSD.1", "EURUSD"),
    ("BTCUSD_2", "BTCUSD"),
    ("ETHUSD-10", "ETHUSD"),
    # Регистр: SPEC.md 6.4 поднимает его до срезания суффикса, поэтому срезается и `.Raw`.
    ("eurusd.m", "EURUSD"),
    ("EurUsd.Raw", "EURUSD"),
    ("usoil.CENT", "USOIL"),
    # Итеративность: суффиксы у брокеров сочетаются, одного прохода не хватает.
    ("EURUSD.m.raw", "EURUSD"),
    ("EURUSD_i.pro", "EURUSD"),
    ("EURUSD.m.m.m.m", "EURUSD"),
    ("US30.m", "US30"),
    ("JP225_i", "JP225"),
    # Символ без суффикса проходит как есть — очистка не обязана что-то менять.
    ("EURUSD", "EURUSD"),
    ("XAUUSD", "XAUUSD"),
)

# Обратная сторона той же таблицы: что правило трогать не имеет права. Здесь живут
# и неудобные исходы — они закреплены не потому, что хороши, а потому, что иначе
# изменятся молча (`docs/mt5-assumptions.md`, допущение 12).
UNTOUCHED_CASES: tuple[tuple[str, str], ...] = (
    # Разделителя нет — суффикса нет. На этом же держатся индексы, см. ниже.
    ("EURUSD+", "EURUSD+"),
    ("EURUSD#", "EURUSD#"),
    # `\d+` требует, чтобы весь хвост после разделителя был цифрами.
    ("EURUSD.M1", "EURUSD.M1"),
    # `.cash` в списке SPEC.md 6.4 не назван, а у брокеров встречается.
    ("DE40.cash", "DE40.CASH"),
    # Разделитель внутри имени: `USD` не альтернатива, и правило до него не доходит.
    ("ETH_USD", "ETH_USD"),
    # Хвост из одного разделителя остаётся: срезать его SPEC.md 6.4 не просит.
    ("EURUSD.", "EURUSD."),
    ("EURUSD..m", "EURUSD."),
    # `upper()` знает Unicode: `ß` разворачивается в две буквы, и имя меняет длину.
    # Брокеров с таким тикером не видели, но испортить имя это способно молча.
    ("ßEURUSD", "SSEURUSD"),
)

# Названия индексов из seed-словаря SPEC.md 6.4 — те самые, что кончаются на цифры.
INDEX_SYMBOLS = ("US30", "US100", "US500", "DE40", "UK100", "JP225")


@pytest.mark.parametrize(("raw", "expected"), SUFFIX_CASES)
def test_broker_suffix_is_stripped(raw: str, expected: str) -> None:
    assert clean_symbol(raw) == expected


@pytest.mark.parametrize(("raw", "expected"), UNTOUCHED_CASES)
def test_what_is_not_a_suffix_stays(raw: str, expected: str) -> None:
    assert clean_symbol(raw) == expected


def test_suffix_table_covers_what_dod_requires() -> None:
    """DoD S1-07: 30 примеров суффиксов. Считает тест, а не глаз ревьюера."""
    assert len(SUFFIX_CASES) >= 30
    assert len(set(SUFFIX_CASES)) == len(SUFFIX_CASES)


# --- индексы: ровно та ловушка, ради которой написан этот файл ------------------------


@pytest.mark.parametrize("symbol", INDEX_SYMBOLS)
def test_index_name_is_not_taken_apart(symbol: str) -> None:
    """`US30` кончается на `\\d+`, и правило обязано его не тронуть."""
    resolved = resolve_symbol(symbol)
    assert resolved.norm == symbol
    assert resolved.asset_class == "index"


@pytest.mark.parametrize("symbol", INDEX_SYMBOLS)
@pytest.mark.parametrize("suffix", (".m", "_i", ".raw", "-c", ".pro", "_1"))
def test_index_with_broker_suffix_collapses_to_the_index(symbol: str, suffix: str) -> None:
    """Суффикс срезается, а цифры имени остаются: `US30.m` → `US30`, а не `US`."""
    assert resolve_symbol(symbol + suffix).norm == symbol


@pytest.mark.parametrize(
    ("raw", "cut_to"),
    (("US_30", "US"), ("US.30", "US"), ("US-30", "US"), ("NIFTY-50", "NIFTY")),
)
def test_separator_before_digits_is_the_only_thing_saving_indices(raw: str, cut_to: str) -> None:
    """Вторая сторона проверки выше: индексы спасает **отсутствие разделителя**, и только оно.

    Тест закрепляет не желаемое, а действительное. Брокер, который назовёт индекс `US_30`,
    получит инструмент `US`, и три его индекса сложатся в один — молча, без ошибки.
    Это допущение 12 в `docs/mt5-assumptions.md`, а не решённая задача.
    """
    assert clean_symbol(raw) == cut_to


@pytest.mark.parametrize("raw", ("BTCUSD.m", "ETHUSD_i", "BTCUSD", "ETHUSD"))
def test_crypto_pairs_survive_the_rule(raw: str) -> None:
    resolved = resolve_symbol(raw)
    assert resolved.asset_class == "crypto"
    assert resolved.norm in {"BTCUSD", "ETHUSD"}


# --- словарь -------------------------------------------------------------------------

# Порядок котировки, по которому строятся мажоры и кроссы: левее стоит валюта выше по
# списку. Набор из SPEC.md 6.4 («мажоры, кроссы») здесь не переписан, а выведен — опечатка
# в словаре (`EURCDA`) перечислением поимённо не ловится: тест повторил бы её за кодом.
QUOTE_ORDER = ("EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF", "JPY")


def test_seed_dictionary_is_exactly_what_spec_lists() -> None:
    expected_fx = {left + right for left, right in combinations(QUOTE_ORDER, 2)}
    by_class: dict[str, set[str]] = {}
    for symbol, asset_class in KNOWN_SYMBOLS.items():
        by_class.setdefault(asset_class, set()).add(symbol)

    assert by_class["fx"] == expected_fx
    assert by_class["metal"] == {"XAUUSD", "XAGUSD"}
    assert by_class["index"] == set(INDEX_SYMBOLS)
    assert by_class["crypto"] == {"BTCUSD", "ETHUSD"}
    assert by_class["energy"] == {"USOIL", "UKOIL"}
    assert set(by_class) == {"fx", "metal", "index", "crypto", "energy"}


@pytest.mark.parametrize("symbol", sorted(KNOWN_SYMBOLS))
def test_every_seed_symbol_is_already_clean(symbol: str) -> None:
    """Ключ словаря обязан быть в очищенном виде — иначе сверка по нему не сработает никогда.

    Ключ вида `EURUSD.m` или `US_30` не совпал бы ни с чем: сверка идёт по `norm`, а не по
    сырому символу. Дефект тихий — словарь на месте, просто половина его не используется.
    """
    assert clean_symbol(symbol) == symbol


# --- незнакомый символ не теряется ---------------------------------------------------


def test_unknown_symbol_keeps_a_cleaned_name_and_falls_back_to_other() -> None:
    resolved = resolve_symbol("XYZ.m")
    assert (resolved.raw, resolved.norm, resolved.asset_class) == ("XYZ.m", "XYZ", "other")


def test_raw_symbol_comes_back_untouched() -> None:
    """`deals.symbol_raw` и `symbols.raw` хранят то, что прислал брокер, вплоть до регистра."""
    assert resolve_symbol("eurusd.m").raw == "eurusd.m"


@pytest.mark.parametrize("raw", (".m", "_1", "-#", ".m.m", "_i"))
def test_cleaning_never_returns_an_empty_name(raw: str) -> None:
    """Символ из одного суффикса очистился бы в пустую строку — инструмент потерял бы имя.

    `symbols.norm` NOT NULL, и по нему фильтрует журнал: пустое имя хуже неузнанного.
    """
    assert clean_symbol(raw)


@pytest.mark.parametrize("raw", [case for case, _ in SUFFIX_CASES + UNTOUCHED_CASES])
def test_cleaning_is_a_fixed_point(raw: str) -> None:
    """Повторная очистка ничего не меняет: иначе `norm` зависел бы от числа синков."""
    once = clean_symbol(raw)
    assert clean_symbol(once) == once


def test_cyrillic_lookalike_stays_a_separate_instrument() -> None:
    """Похожая буква не приводится к латинской — и это заявлено, а не забыто.

    `ЕURUSD.m` с кириллической `Е` попадёт в журнал отдельным инструментом с `other`.
    SPEC.md 6.4 приведения не требует, а замена букв наугад портит имя ровно тем способом,
    от которого защищает весь остальной файл. Допущение — в `docs/mt5-assumptions.md`.
    """
    resolved = resolve_symbol("ЕURUSD.m")

    assert resolved.norm != "EURUSD"
    assert resolved.asset_class == UNKNOWN_ASSET_CLASS


# --- чистота: проверено, а не заявлено -----------------------------------------------

# Механизм разбора исходника — `tests/purity.py`, общий с S1-02. Здесь остаётся контракт:
# то, без чего нормализацию имени не написать. `re` — единственная уступка внешнему миру,
# и она вычислительная: ни часов, ни окружения, ни ввода-вывода за ней нет.
SYMBOLS_PURITY = PurityContract(
    allowed_imports=frozenset({"__future__", "collections.abc", "dataclasses", "re", "typing"}),
    allowed_builtins=frozenset({"str"}),
)


def test_symbols_imports_nothing_impure() -> None:
    assert imported_modules(module_tree(symbols)) <= SYMBOLS_PURITY.allowed_imports


def test_symbols_takes_nothing_from_outside_beyond_imports_and_plain_builtins() -> None:
    tree = module_tree(symbols)
    assert [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)], (
        "модуль обязан определять функции, иначе тест ничего не проверяет"
    )
    assert external_names(tree) <= SYMBOLS_PURITY.allowed_builtins


def test_symbols_never_reaches_for_clock_environment_or_io() -> None:
    tree = module_tree(symbols)
    assert leaks(tree, SYMBOLS_PURITY) == set()
    # Иначе дыру можно открыть, дописав `now` в белый список, и оба теста останутся зелёными.
    assert SYMBOLS_PURITY.allowed_builtins.isdisjoint(IMPURE_NAMES)
    assert bound_names(tree).isdisjoint(SYMBOLS_PURITY.guarded), (
        "модуль затеняет имя, на котором держится проверка"
    )


@pytest.mark.parametrize("case", sorted(IMPURE_SNIPPETS))
def test_purity_check_is_not_vacuous_for_this_contract(case: str) -> None:
    """Проверка проверки: три известных обхода обязаны быть красными и на этом контракте.

    Белый список у каждого модуля свой, поэтому наследовать результат S1-02 нельзя:
    контракт, в котором разрешён `getattr`, пропустил бы третий обход молча.
    """
    assert leaks(ast.parse(IMPURE_SNIPPETS[case]), SYMBOLS_PURITY)
