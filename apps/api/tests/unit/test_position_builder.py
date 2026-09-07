"""Сборка позиций из сделок брокера (S1-03, SPEC.md 7).

Проверяется то, что молчит. Неверно сложенный объём, потерянная копейка комиссии или
плавающая прибыль, попавшая в `net_pnl` открытой позиции, не роняют ни один запрос — они
показывают пользователю неверное число и находятся в сверке с отчётом терминала недели
спустя (S1-12).

Половина фикстур здесь — настоящие сделки боевого счёта (выгрузка 7 сентября 2026),
половина выдумана, потому что соответствующего случая в выгрузке нет вовсе. Разница
принципиальная и подписана в каждом файле полем `origin`: на настоящих проверяется, что
код работает на данных брокера, на выдуманных — что он следует спеке. Происхождение
каждой — `docs/fixtures.md`.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft7Validator
from purity import (
    IMPURE_NAMES,
    PurityContract,
    bound_names,
    external_names,
    imported_modules,
    leaks,
    module_tree,
)

from app.domains.ingest import position_builder
from app.domains.ingest.normalizer import NormalizedDeal, normalize_batch, normalize_deal
from app.domains.ingest.position_builder import (
    FOREIGN_OPEN_POSITION,
    MIXED_POSITIONS,
    NO_DEALS,
    NO_ENTRY_VOLUME,
    NON_POSITION_DEAL,
    BuiltPosition,
    OpenPositionSnapshot,
    PositionBuildError,
    build_position,
    group_position_deals,
    open_position_snapshot,
    quantize_money,
)
from app.domains.ingest.schema_export import SCHEMA_PATH
from app.domains.ingest.schemas import IngestDeal, IngestDealsBatch, IngestOpenPosition

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/deals"

# Восемь фикстур, которых SPEC.md 7 требует поимённо. Карта нужна затем, что список в
# спеке — единственное место, где эти случаи перечислены: без сверки набор мог бы тихо
# похудеть на случай, который никто не помнит.
SPEC_SEVEN_CASES = {
    "простая long-сделка": "real-simple-long.json",
    "short с SL": "real-short-with-sl.json",
    "частичное закрытие в 3 приёма": "real-partial-close-in-three.json",
    "доливка + закрытие": "synthetic-scale-in-and-close.json",
    "переворот на неттинге": "synthetic-netting-reversal.json",
    "позиция с корректировкой other": "synthetic-adjustment-other.json",
    "открытая позиция без выхода": "synthetic-open-position.json",
    "два батча с перекрытием": "real-two-batches-overlap.json",
}

# Сверх перечня спеки. Оба — настоящие сделки, и оба про то, чего спека не перечисляла.
EXTRA_CASES = {
    "real-partial-close-in-four.json": "самая длинная настоящая позиция: вход и четыре выхода",
    "real-deposit-is-not-a-position.json": "депозит в батче не становится позицией (X-44)",
}

OFFSET = 120


def fixture(name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return document


def fixture_names() -> list[str]:
    return sorted(path.name for path in FIXTURES.glob("*.json"))


def built_positions(document: dict[str, Any]) -> dict[int, BuiltPosition]:
    """Батчи фикстуры — как их увидел бы S1-04: граница, нормализация, накопление, сборка.

    Накопление именно словарём по `deal_ticket`: это `unique (account_id, deal_ticket)`
    из SPEC.md 3.3 в миниатюре. Перекрывающиеся батчи — норма, и повторная сделка обязана
    не создавать второй строки, иначе объём позиции удвоится.
    """
    stored: dict[int, NormalizedDeal] = {}
    snapshots: dict[int, OpenPositionSnapshot] = {}
    for body in document["batches"]:
        parsed = IngestDealsBatch.model_validate(body)
        for item in normalize_batch(parsed).deals:
            stored.setdefault(item.deal_ticket, item)
        snapshots = {
            record.position_id: open_position_snapshot(record) for record in parsed.open_positions
        }
    return {
        position_id: build_position(deals, open_position=snapshots.get(position_id))
        for position_id, deals in group_position_deals(stored.values()).items()
    }


def as_expected(position: BuiltPosition) -> dict[str, Any]:
    """Строка в том же виде, в каком ожидания записаны в фикстуре."""
    document: dict[str, Any] = {}
    for item in fields(BuiltPosition):
        value = getattr(position, item.name)
        if isinstance(value, Decimal):
            # `format(..., "f")`, а не `str`: у нуля с масштабом `str` даёт «0E-8», и
            # фикстура выглядела бы страннее, чем колонка, которую она описывает.
            document[item.name] = format(value, "f")
        elif isinstance(value, datetime):
            document[item.name] = value.isoformat().replace("+00:00", "Z")
        else:
            document[item.name] = value
    return document


def deal_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ticket": 1,
        "order": 10,
        "position_id": 100,
        "type": 0,
        "symbol": "EURUSD",
        "entry": 0,
        "reason": 3,
        "volume": "0.10",
        "price": "1.10000",
        "profit": "0",
        "commission": "0",
        "swap": "0",
        "fee": "0",
        "time_server": "2026-03-02T10:00:00",
        "comment": "",
        "magic": 0,
    }
    body.update(overrides)
    moment = datetime.fromisoformat(body["time_server"]).replace(tzinfo=UTC)
    body.setdefault("time_msc", int(moment.timestamp()) * 1000)
    return body


def deal(**overrides: Any) -> NormalizedDeal:
    return normalize_deal(
        IngestDeal.model_validate(deal_body(**overrides)), server_utc_offset_minutes=OFFSET
    )


# --- набор фикстур ------------------------------------------------------------------


def test_every_case_named_by_spec_7_has_a_fixture() -> None:
    assert set(SPEC_SEVEN_CASES.values()) <= set(fixture_names())


def test_no_fixture_lies_around_undescribed() -> None:
    """Файл без объяснения — фикстура, про которую через месяц никто не скажет, зачем она."""
    assert set(fixture_names()) == set(SPEC_SEVEN_CASES.values()) | set(EXTRA_CASES)


@pytest.mark.parametrize("name", fixture_names())
def test_fixture_declares_where_it_came_from(name: str) -> None:
    """`origin` — не украшение: на настоящих проверяется работа на данных брокера, на
    выдуманных — следование спеке, и путать их нельзя."""
    document = fixture(name)

    assert document["origin"] in ("real", "synthetic")
    assert document["origin"] == ("real" if name.startswith("real-") else "synthetic")
    assert document["title"] and document["source"] and document["notes"]


@pytest.mark.parametrize("name", fixture_names())
def test_fixture_carries_no_payment_identifier(name: str) -> None:
    """Обезличивание: в комментарии настоящего депозита стоял внутренний номер платежа.

    Проверка идёт по форме, а не по конкретному значению: караулить утечку строкой,
    которая сама эту строку в репозиторий и вносит, — способ не заметить собственную
    ошибку. Комментарии брокера у нас короткие и без цифр (`MarketBuy`, `LimitSell[sl]`,
    `Deposit`), поэтому длинный ряд цифр в них означает чей-то идентификатор.
    """
    document = fixture(name)

    for batch in document["batches"]:
        for deal in batch["deals"]:
            comment = deal.get("comment", "")
            assert not re.search(r"\d{5,}", comment), (name, comment)
            assert ":" not in comment, (name, comment)


@pytest.mark.parametrize("name", fixture_names())
def test_fixture_batches_satisfy_the_published_contract(name: str) -> None:
    """Смысл X-44 на настоящих данных: батч с депозитом проходит опубликованный контракт.

    Проверяется не модель, а файл `ingest-deals.schema.json` — им пользуется отправитель
    вне Python, и именно он до X-44 объявлял пустой символ невалидным.
    """
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft7Validator(schema)

    for body in fixture(name)["batches"]:
        assert list(validator.iter_errors(body)) == []


@pytest.mark.parametrize("name", fixture_names())
def test_fixture_builds_exactly_the_expected_positions(name: str) -> None:
    """Главный тест задачи: ожидания записаны в фикстуре и посчитаны независимо от кода."""
    document = fixture(name)
    positions = built_positions(document)
    expected = {item["position_id"]: item for item in document["expected"]}

    assert set(positions) == set(expected), "собрались не те позиции, что ожидались"
    for position_id, position in positions.items():
        assert as_expected(position) == expected[position_id]


@pytest.mark.parametrize("name", fixture_names())
def test_rebuilding_the_same_deals_gives_the_same_row(name: str) -> None:
    """Пересборка идемпотентна (SPEC.md 7): второй прогон обязан дать ту же строку."""
    document = fixture(name)

    assert built_positions(document) == built_positions(document)


@pytest.mark.parametrize("name", fixture_names())
def test_order_of_the_input_does_not_change_the_row(name: str) -> None:
    """Порядок сделок задаёт вызывающий, а результат от него зависеть не должен.

    Иначе идемпотентность пересборки держалась бы на `ORDER BY` в чужом запросе.
    """
    document = fixture(name)
    reversed_batches = {
        **document,
        "batches": [
            {**body, "deals": list(reversed(body["deals"]))} for body in document["batches"]
        ],
    }

    assert built_positions(reversed_batches) == built_positions(document)


def test_two_overlapping_batches_give_what_one_batch_would() -> None:
    """Перекрытие окон — норма синка, а не сбой (SPEC.md 8.2), и следа оставлять не должно.

    Коллектор перезапрашивает `last_sync_at − 24h`, и средняя сделка приезжает дважды.
    Учтись она дважды — объём закрытия вырос бы, а позиция перестала бы сходиться.
    """
    document = fixture("real-two-batches-overlap.json")
    tickets = [item["ticket"] for body in document["batches"] for item in body["deals"]]
    merged = {
        **document,
        "batches": [{**document["batches"][0], "deals": _unique_deals(document["batches"])}],
    }

    assert len(tickets) != len(set(tickets)), "фикстура обязана содержать повтор"
    assert built_positions(document) == built_positions(merged)


def _unique_deals(batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[int, dict[str, Any]] = {}
    for body in batches:
        for item in body["deals"]:
            unique.setdefault(item["ticket"], item)
    return list(unique.values())


# --- net_pnl открытой позиции -------------------------------------------------------


def test_open_position_keeps_costs_not_floating_profit() -> None:
    """Решение, на котором держится сводка S2-05 (`docs/mt5-assumptions.md`, допущение 20).

    Батч приносит плавающий результат открытой позиции, и в `net_pnl` его быть не должно:
    иначе объяснение «шапка журнала не сходится с колонкой на сумму открытых» превратится
    в число, меняющееся от котировки к котировке.
    """
    positions = built_positions(fixture("synthetic-open-position.json"))
    position = positions[800031]

    assert position.status == "open"
    assert position.net_pnl == Decimal("-1.40")
    assert position.net_pnl == position.commission
    assert position.gross_pnl == Decimal("0.00")


def test_the_snapshot_cannot_carry_floating_profit() -> None:
    """Не обещание, а свойство типа: пронести плавающую прибыль в сборщик нечем."""
    record = IngestOpenPosition.model_validate(
        {
            "position_id": 800031,
            "symbol": "GBPUSD",
            "type": 0,
            "volume": "0.20",
            "price_open": "1.30000",
            "time_server": "2026-03-06T08:30:00",
            "sl": "0",
            "tp": "0",
            "profit": "137.50",
        }
    )

    snapshot = open_position_snapshot(record)

    assert [item.name for item in fields(OpenPositionSnapshot)] == ["position_id"]
    assert not hasattr(snapshot, "profit")


def test_balanced_volume_alone_does_not_close_a_position() -> None:
    """SPEC.md 7 требует обоих условий: объём сошёлся И записи в open_positions нет."""
    deals = [
        deal(ticket=1, entry=0, type=0, volume="0.10"),
        deal(ticket=2, entry=1, type=1, volume="0.10", time_server="2026-03-02T12:00:00"),
    ]

    closed = build_position(deals)
    still_open = build_position(deals, open_position=OpenPositionSnapshot(position_id=100))

    assert closed.status == "closed"
    assert closed.close_time is not None
    assert still_open.status == "open"
    assert still_open.close_time is None, "у открытой позиции времени закрытия быть не может"
    assert still_open.duration_seconds is None


# --- алгоритм SPEC.md 7 -------------------------------------------------------------


def test_netting_reversal_closes_the_position_and_drops_the_remainder() -> None:
    """`inout` 1.50 при открытых 1.00 закрывает 1.00; остаток новой позиции не создаёт."""
    position = built_positions(fixture("synthetic-netting-reversal.json"))[800011]

    assert position.volume_closed == Decimal("1.00000000")
    assert position.volume_opened == Decimal("1.00000000")
    assert position.status == "closed"
    assert position.close_reason is None


def test_adjustment_adds_money_but_not_volume_or_count() -> None:
    """`other` с ненулевым `position_id`: деньги — да, объём и `deals_count` — нет."""
    position = built_positions(fixture("synthetic-adjustment-other.json"))[800021]

    assert position.deals_count == 2
    assert position.commission == Decimal("-4.25")
    assert position.volume_opened == Decimal("0.50000000")
    assert position.close_time == datetime(2026, 3, 5, 10, 0, tzinfo=UTC)


def test_partial_exits_give_a_weighted_average_price() -> None:
    """Вторая сделка выхода — не закрытие целиком: объём складывается, цена взвешивается."""
    position = built_positions(fixture("real-partial-close-in-four.json"))[195286839]

    assert position.deals_count == 5
    assert position.volume_closed == Decimal("0.20000000")
    assert position.avg_exit_price == Decimal("1.34309850")


def test_deposit_does_not_become_a_position() -> None:
    """SPEC.md 6.2 и настоящие данные: у пополнения `position_id = 0`, позиции из него нет."""
    document = fixture("real-deposit-is-not-a-position.json")
    tickets = {item["ticket"] for item in document["batches"][0]["deals"]}

    positions = built_positions(document)

    assert 104238311 in tickets, "фикстура обязана содержать сам депозит"
    assert set(positions) == {120385937}


def test_close_reason_comes_from_reason_not_from_the_comment() -> None:
    """Находка выгрузки, закреплённая тестом: у этого брокера `reason` про стоп не знает.

    Выходная сделка помечена `LimitSell[sl]`, а `reason` у неё 0 (клиент). SPEC.md 7
    велит брать причину из `reason`, и код берёт из `reason` — значит `close_reason`
    здесь `client`. Правило спеки не менялось; тест фиксирует, чего оно стоит.
    """
    document = fixture("real-short-with-sl.json")
    exit_deal = document["batches"][0]["deals"][1]

    position = built_positions(document)[119002027]

    assert "[sl]" in exit_deal["comment"]
    assert exit_deal["reason"] == 0
    assert position.close_reason == "client"


def test_trading_deal_without_a_position_id_still_makes_a_position() -> None:
    """Развилка, переданная из S1-02: `buy` с нулевым `position_id`.

    SPEC.md 6.2 исключает из сборки `balance`, `credit` и `other`; про торговую сделку с
    нулём там нет ни слова, и в выгрузке 7 сентября 2026 такого не встретилось ни разу
    (все 503 торговые несут позицию). Отбрасывать её — правило, которого в спеке нет:
    сделка исчезла бы из журнала молча. Поэтому позиция собирается.
    """
    deals = [
        deal(ticket=1, position_id=0, entry=0, type=0, volume="0.10"),
        deal(
            ticket=2,
            position_id=0,
            entry=1,
            type=1,
            volume="0.10",
            profit="5.00",
            time_server="2026-03-02T12:00:00",
        ),
    ]

    grouped = group_position_deals(deals)

    assert set(grouped) == {0}
    assert build_position(grouped[0]).net_pnl == Decimal("5.00")


def test_grouping_drops_what_spec_6_2_excludes() -> None:
    """`balance` и `credit` не участвуют в сборке ни при каком `position_id`."""
    deals = [
        deal(ticket=1, position_id=100, entry=0, type=0),
        deal(ticket=2, position_id=0, type=2, volume="0", price="0", profit="615.46"),
        deal(ticket=3, position_id=100, type=3, volume="0", price="0", profit="10.00"),
        deal(ticket=4, position_id=100, type=7, volume="0", price="0", commission="-1.25"),
    ]

    grouped = group_position_deals(deals)

    assert set(grouped) == {100}
    assert [item.deal_ticket for item in grouped[100]] == [1, 4]


# --- округление ---------------------------------------------------------------------


def test_money_is_rounded_per_deal_not_after_the_sum() -> None:
    """Где округляется — решение, а не деталь реализации.

    Две сделки по 0.005: поштучно это 0.01 + 0.01 = 0.02, а округление суммы дало бы
    0.01. В БД каждая сделка ляжет в numeric(18,2) уже округлённой, поэтому позиция
    обязана складывать те же значения, что сохранены, — иначе она разойдётся с суммой
    собственных сделок, а S1-12 требует сойтись с отчётом терминала в 0,00.
    """
    deals = [
        deal(ticket=1, entry=0, type=0, volume="0.10", profit="0.005"),
        deal(
            ticket=2,
            entry=1,
            type=1,
            volume="0.10",
            profit="0.005",
            time_server="2026-03-02T12:00:00",
        ),
    ]

    position = build_position(deals)

    assert position.gross_pnl == Decimal("0.02")
    assert quantize_money(Decimal("0.005") + Decimal("0.005")) == Decimal("0.01")


def test_float64_noise_of_the_broker_becomes_the_number_it_meant() -> None:
    """`-1.6099999999999999` — это `-1.61`: шум float64, а не третий знак комиссии."""
    position = built_positions(fixture("real-partial-close-in-three.json"))[129369078]

    assert position.gross_pnl == Decimal("9.16")
    assert position.net_pnl == Decimal("9.31")


def test_every_money_and_quantity_lands_on_the_column_scale() -> None:
    """Значение не того масштаба доехало бы до Postgres и вернулось пятисоткой."""
    for name in fixture_names():
        for position in built_positions(fixture(name)).values():
            for item in ("gross_pnl", "commission", "swap", "fee", "net_pnl"):
                value: Decimal = getattr(position, item)
                assert value.as_tuple().exponent == -2, f"{name}.{item}"
            for item in ("volume_opened", "volume_closed", "avg_entry_price"):
                value = getattr(position, item)
                assert value.as_tuple().exponent == -8, f"{name}.{item}"


def test_net_pnl_is_the_sum_of_its_parts_in_every_fixture() -> None:
    """SPEC.md 3.3: `net_pnl = gross + commission + swap + fee`, знаки как у брокера."""
    for name in fixture_names():
        for position in built_positions(fixture(name)).values():
            parts = position.gross_pnl + position.commission + position.swap + position.fee
            assert position.net_pnl == parts, name


# --- отказы -------------------------------------------------------------------------


def test_empty_input_is_refused() -> None:
    with pytest.raises(PositionBuildError, match=NO_DEALS):
        build_position([])


def test_deals_of_two_positions_are_refused() -> None:
    """Слить две позиции в одну строку — потерять обе; молчать об этом нельзя."""
    deals = [deal(ticket=1, position_id=100), deal(ticket=2, position_id=101)]

    with pytest.raises(PositionBuildError, match=MIXED_POSITIONS):
        build_position(deals)


def test_snapshot_of_another_position_is_refused() -> None:
    with pytest.raises(PositionBuildError, match=FOREIGN_OPEN_POSITION):
        build_position([deal(ticket=1)], open_position=OpenPositionSnapshot(position_id=999))


def test_non_position_deal_is_refused() -> None:
    """Пополнение, попавшее в группу, — ошибка вызывающего, а не повод тихо его пропустить."""
    deals = [deal(ticket=1, position_id=100), deal(ticket=2, position_id=100, type=2)]

    with pytest.raises(PositionBuildError, match=re.escape(NON_POSITION_DEAL)):
        build_position(deals)


def test_position_without_an_entry_is_refused() -> None:
    """Окно синхронизации может не захватить вход: делить на нулевой объём нечего.

    Отказ, а не строка с нулями: что делать с такой группой, решает S1-04 — у него есть
    и лог, и `sync_runs`, а у чистой функции нет ни того, ни другого.
    """
    deals = [deal(ticket=2, entry=1, type=1, volume="0.10", profit="5.00")]

    with pytest.raises(PositionBuildError, match=NO_ENTRY_VOLUME):
        build_position(deals)


# --- чистота ------------------------------------------------------------------------

# Механизм разбора исходника — `tests/purity.py`, общий с нормализатором и символами.
# Здесь контракт: ровно то, без чего сборщик не написать. Любой новый импорт делает тест
# красным и заставляет объяснить, зачем чистой функции понадобился внешний мир.
BUILDER_PURITY = PurityContract(
    allowed_imports=frozenset(
        {
            "__future__",
            "app.domains.ingest.normalizer",
            "app.domains.ingest.schemas",
            "collections.abc",
            "dataclasses",
            "datetime",
            "decimal",
            "typing",
        }
    ),
    allowed_builtins=frozenset(
        {"ValueError", "any", "dict", "int", "list", "min", "property", "sorted", "str", "tuple"}
    ),
)


def test_builder_imports_nothing_impure() -> None:
    assert imported_modules(module_tree(position_builder)) <= BUILDER_PURITY.allowed_imports


def test_builder_takes_nothing_from_outside_beyond_imports_and_plain_builtins() -> None:
    tree = module_tree(position_builder)
    assert [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)], (
        "модуль обязан определять функции, иначе тест ничего не проверяет"
    )
    assert external_names(tree) <= BUILDER_PURITY.allowed_builtins


def test_builder_never_reaches_for_clock_environment_or_io() -> None:
    tree = module_tree(position_builder)
    assert leaks(tree, BUILDER_PURITY) == set()
    # Иначе дыру можно открыть, дописав `now` в белый список, и оба теста остались бы зелёными.
    assert BUILDER_PURITY.allowed_builtins.isdisjoint(IMPURE_NAMES)
    assert bound_names(tree).isdisjoint(BUILDER_PURITY.guarded), (
        "модуль затеняет имя, на котором держится проверка"
    )


def test_builder_does_no_decimal_arithmetic_by_operator() -> None:
    """Урок S2-05: операторы над `Decimal` считают в контексте потока, а его меняет кто угодно.

    Здесь это ловится по исходнику, потому что враждебный контекст на суммах денег
    проявился бы не всегда: точность по умолчанию 28 знаков, и разойтись такой расчёт
    может на данных, которых в тестах нет.
    """
    tree = module_tree(position_builder)
    arithmetic = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)

    offenders = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and isinstance(node.op, arithmetic)
    ]

    # Единственное исключение и оно записано: вычитание моментов времени контекста
    # `decimal` не касается, а посчитать длительность иначе нечем. Список точный, а не
    # «кроме datetime»: новая арифметика проступит в нём сразу.
    assert offenders == ["close_time - open_time"], "арифметика обязана идти через POSITION_CONTEXT"
