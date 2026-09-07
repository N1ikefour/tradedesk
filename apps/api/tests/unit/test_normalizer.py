"""Нормализация deals из MT5 (S1-02, SPEC.md 6.2–6.3).

Проверяется то, что молчит: маппинги перечислений, перевод времени сервера брокера в UTC
и роль сделки в сборке позиции. Ошибка в любом из трёх не роняет ингест — она пишет в
базу не то число, поэтому здесь каждая строка таблицы §6.2 проверена отдельно. Чистота
при этом остаётся требованием, а не доказанным свойством: проверены четыре конкретные
вещи, а не все возможные обходы. Механизм проверки — `tests/purity.py`, контракт
нормализатора — `NORMALIZER_PURITY` ниже.
"""

from __future__ import annotations

import ast
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal
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

from app.domains.ingest import normalizer
from app.domains.ingest.normalizer import (
    DEAL_TYPE_BY_CODE,
    DOCUMENTED_OTHER_DEAL_TYPE_CODES,
    DOCUMENTED_OTHER_REASON_CODES,
    ENTRY_BY_CODE,
    REASON_BY_CODE,
    SERVER_TIME_NOT_NAIVE,
    DealRole,
    DealType,
    NormalizedDeal,
    UnknownCode,
    deal_role,
    label_server_time,
    normalize_batch,
    normalize_deal,
    normalize_deal_type,
    normalize_entry,
    normalize_reason,
    to_utc,
)
from app.domains.ingest.schemas import TRADING_DEAL_TYPE_CODES, IngestDeal, IngestDealsBatch

ACCOUNT_ID = "0199a5c1-7d7a-7c3e-8f2a-1b2c3d4e5f60"


def _msc(time_server: str) -> int:
    """`time_msc` из `time_server`: S1-01 требует, чтобы два поля сходились."""
    return int(datetime.fromisoformat(time_server).replace(tzinfo=UTC).timestamp()) * 1000


def deal_body(**overrides: Any) -> dict[str, Any]:
    """Умолчания попарно различны — это несущее свойство, а не аккуратность.

    Совпадающие значения делают подмену источника невидимой: пока `order` равен
    `position_id`, а `volume` — `price`, тест не отличит правильный маппинг от
    перепутанного. Различность закреплена `test_fixture_defaults_are_pairwise_distinct`.
    """
    body: dict[str, Any] = {
        "ticket": 1001,
        "order": 2002,
        "position_id": 3003,
        "symbol": "EURUSD.m",
        "type": 1,
        "entry": 2,
        "reason": 5,
        "volume": "0.10",
        "price": "1.08543",
        "profit": "12.34",
        "commission": "-0.35",
        "swap": "-1.20",
        "fee": "-0.07",
        "time_server": "2026-09-02T14:03:11",
        "comment": "sl 1.0800",
        "magic": 4004,
    }
    body.update(overrides)
    if "time_msc" not in overrides:
        body["time_msc"] = _msc(body["time_server"])
    return body


def deal(**overrides: Any) -> IngestDeal:
    return IngestDeal.model_validate(deal_body(**overrides))


def batch(bodies: list[dict[str, Any]], offset: int = 180) -> IngestDealsBatch:
    return IngestDealsBatch.model_validate(
        {
            "account_id": ACCOUNT_ID,
            "source": "collector",
            "server_utc_offset_minutes": offset,
            "account_info": {
                "currency": "USD",
                "margin_mode": "hedging",
                "balance": "10000.00",
                "equity": "10012.50",
            },
            "deals": bodies,
            "open_positions": [],
        }
    )


# --- Каждое поле из своего источника (SPEC.md 3.3) ----------------------------------


def test_fixture_defaults_are_pairwise_distinct() -> None:
    """Условие, без которого нижний тест ничего не доказывает.

    Одинаковые умолчания превращают проверку маппинга в тавтологию: перепутанные местами
    поля дают то же самое значение, и тест остаётся зелёным.
    """
    values = [str(value) for value in deal_body().values()]
    assert len(set(values)) == len(values)


def test_every_normalized_field_comes_from_its_own_source_field() -> None:
    """Все поля `NormalizedDeal` разом, каждое со своим ни на что не похожим значением.

    Подмена источника (`position_id = deal.order`, `volume = deal.price`) не падает и не
    выглядит подозрительно: значение правдоподобное, просто чужое. Ловит её только сверка
    всех полей сразу при попарно различных входах. Цена ошибки известна заранее:
    `position_id` — ключ группировки всей сборки позиций (S1-03), `volume` — вход
    `opened`/`closed`/`avg_entry` (SPEC.md 7).

    Сравнение множества имён с `fields(NormalizedDeal)` держит тест полным: новое поле
    DTO делает его красным, а не молча остаётся непроверенным.
    """
    body = deal_body(
        ticket=7000001,
        order=7000002,
        position_id=7000003,
        magic=7000004,
        symbol="XAUUSD.pro",
        type=1,  # sell
        entry=2,  # inout
        reason=5,  # tp
        volume="0.37",
        price="2451.19",
        profit="128.40",
        commission="-0.35",
        swap="-1.20",
        fee="-0.07",
        time_server="2026-09-02T14:03:11",
        comment="tp 2450",
    )
    normalized = normalize_deal(IngestDeal.model_validate(body), server_utc_offset_minutes=180)

    expected: dict[str, Any] = {
        "deal_ticket": 7000001,
        "order_ticket": 7000002,
        "position_id": 7000003,
        "magic": 7000004,
        "symbol_raw": "XAUUSD.pro",
        "deal_type": "sell",
        "entry": "inout",
        "reason": "tp",
        "volume": Decimal("0.37"),
        "price": Decimal("2451.19"),
        "profit": Decimal("128.40"),
        "commission": Decimal("-0.35"),
        "swap": Decimal("-1.20"),
        "fee": Decimal("-0.07"),
        "time_utc": datetime(2026, 9, 2, 11, 3, 11, tzinfo=UTC),
        "time_server": datetime(2026, 9, 2, 14, 3, 11, tzinfo=UTC),
        "comment": "tp 2450",
        "raw": body,
    }

    assert {item.name for item in fields(NormalizedDeal)} == set(expected), (
        "у NormalizedDeal появилось или пропало поле, которого этот тест не сверяет"
    )
    distinct = [str(value) for value in expected.values()]
    assert len(set(distinct)) == len(distinct), "ожидания обязаны быть попарно различны"
    assert {name: getattr(normalized, name) for name in expected} == expected


# --- Маппинг перечислений (SPEC.md 6.2) ---------------------------------------------


def test_enum_tables_match_spec_6_2_line_by_line() -> None:
    """Сами таблицы, а не только поведение: подмена значения обязана быть красной."""
    assert dict(DEAL_TYPE_BY_CODE) == {0: "buy", 1: "sell", 2: "balance", 3: "credit"}
    assert dict(ENTRY_BY_CODE) == {0: "in", 1: "out", 2: "inout", 3: "out_by"}
    assert dict(REASON_BY_CODE) == {
        0: "client",
        1: "mobile",
        2: "web",
        3: "expert",
        4: "sl",
        5: "tp",
        6: "so",
    }


def test_boundary_knows_the_same_trading_codes_as_the_mapping() -> None:
    """Единственная копия таблицы 6.2 вне этого модуля — и она обязана совпадать.

    Граница (`schemas.py`) не вправе импортировать нормализатор: он импортирует её.
    Поэтому набор торговых кодов, по которому X-44 решает, обязателен ли инструмент,
    записан там отдельно. Разъедься он с маппингом — и послабление начало бы пускать
    торговую сделку без символа, не покраснев нигде.
    """
    trading = {code for code, name in DEAL_TYPE_BY_CODE.items() if name in ("buy", "sell")}

    assert trading == set(TRADING_DEAL_TYPE_CODES)


@pytest.mark.parametrize(
    ("code", "expected"),
    [(0, "buy"), (1, "sell"), (2, "balance"), (3, "credit")],
)
def test_deal_type_known_codes(code: int, expected: DealType) -> None:
    assert normalize_deal_type(code) == expected


@pytest.mark.parametrize(
    "code",
    [
        4,  # CHARGE
        5,  # CORRECTION
        6,  # BONUS
        7,  # COMMISSION
        12,  # INTEREST
        17,  # TAX
        99,  # такого в перечислении нет вовсе
        2**31,  # заведомо большое число
    ],
)
def test_deal_type_everything_else_is_other(code: int) -> None:
    assert normalize_deal_type(code) == "other"


@pytest.mark.parametrize(
    ("code", "expected"),
    [(0, "in"), (1, "out"), (2, "inout"), (3, "out_by")],
)
def test_entry_covers_the_whole_enum(code: int, expected: str) -> None:
    assert normalize_entry(code) == expected


def test_entry_outside_the_enum_fails_loudly() -> None:
    """Fallback'а нет намеренно: 0..3 гарантирует граница S1-01 (`schemas.py`).

    Тест фиксирует не защиту, а её отсутствие: код вне диапазона означает сломанную
    границу, и это должно быть видно, а не превращено в правдоподобное значение.
    """
    with pytest.raises(KeyError):
        normalize_entry(4)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (0, "client"),
        (1, "mobile"),
        (2, "web"),
        (3, "expert"),
        (4, "sl"),
        (5, "tp"),
        (6, "so"),
    ],
)
def test_reason_known_codes(code: int, expected: str) -> None:
    assert normalize_reason(code) == expected


@pytest.mark.parametrize("code", [7, 8, 9, 10, 42, 2**31])
def test_reason_everything_else_is_other(code: int) -> None:
    assert normalize_reason(code) == "other"


# --- Роль в сборке позиции (SPEC.md 6.2, последний абзац) ---------------------------


def test_other_with_position_id_is_an_adjustment_of_that_position() -> None:
    """Случай, который DoD называет отдельно.

    `other` ведёт себя двояко в зависимости от постороннего поля: при `position_id = 0`
    это операция по счёту, при `position_id ≠ 0` — комиссия или корректировка, деньги
    которой обязаны попасть в позицию (SPEC.md 7, `gross_pnl`).
    """
    normalized = normalize_deal(
        deal(
            type=7,  # COMMISSION → 'other'
            position_id=123456700,
            entry=1,
            volume="0",
            profit="-2.50",
            commission="-0.70",
            swap="-1.20",
            fee="-0.30",
        ),
        server_utc_offset_minutes=0,
    )

    assert normalized.deal_type == "other"
    assert deal_role(normalized.deal_type, normalized.position_id) == "adjustment"
    assert normalized.profit == Decimal("-2.50")
    assert normalized.commission == Decimal("-0.70")
    assert normalized.swap == Decimal("-1.20")
    assert normalized.fee == Decimal("-0.30")


def test_other_without_position_id_stays_out_of_positions() -> None:
    assert deal_role("other", 0) == "excluded"


@pytest.mark.parametrize(
    ("deal_type", "position_id", "expected"),
    [
        ("buy", 123456700, "trade"),
        ("sell", 123456700, "trade"),
        # Развилка, переданная в S1-03 (docs/mt5-assumptions.md, пункт 8): §6.2 исключает
        # только balance, credit и other, про торговую сделку с нулевым position_id там нет
        # ни слова. Значит она остаётся trade — отбрасывать её было бы правилом, которого в
        # спеке нет. Решение документировано, и потому обязано быть закреплено.
        ("buy", 0, "trade"),
        ("sell", 0, "trade"),
        ("balance", 0, "excluded"),
        ("credit", 0, "excluded"),
        # SPEC.md 6.2 исключает balance и credit безусловно, а не «когда position_id = 0».
        ("balance", 123456700, "excluded"),
        ("credit", 123456700, "excluded"),
        ("other", 0, "excluded"),
        ("other", 123456700, "adjustment"),
    ],
)
def test_deal_role_matrix(deal_type: DealType, position_id: int, expected: DealRole) -> None:
    assert deal_role(deal_type, position_id) == expected


# --- Время (SPEC.md 6.3) ------------------------------------------------------------


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (180, datetime(2026, 9, 2, 11, 3, 11, tzinfo=UTC)),
        (0, datetime(2026, 9, 2, 14, 3, 11, tzinfo=UTC)),
        (-300, datetime(2026, 9, 2, 19, 3, 11, tzinfo=UTC)),
        (840, datetime(2026, 9, 2, 0, 3, 11, tzinfo=UTC)),
        (-720, datetime(2026, 9, 3, 2, 3, 11, tzinfo=UTC)),
    ],
)
def test_to_utc_subtracts_the_offset(offset: int, expected: datetime) -> None:
    assert to_utc(datetime(2026, 9, 2, 14, 3, 11), offset) == expected


def test_to_utc_crosses_midnight_backwards() -> None:
    """Сделка 2 сентября в 00:30 при offset +180 — это 1 сентября по UTC.

    Ошибка здесь уводит позицию в соседний торговый день, где пользователь её не найдёт.
    """
    assert to_utc(datetime(2026, 9, 2, 0, 30, 0), 180) == datetime(
        2026, 9, 1, 21, 30, 0, tzinfo=UTC
    )


def test_to_utc_crosses_midnight_forwards() -> None:
    assert to_utc(datetime(2026, 9, 2, 23, 30, 0), -180) == datetime(
        2026, 9, 3, 2, 30, 0, tzinfo=UTC
    )


def test_to_utc_returns_aware_utc() -> None:
    result = to_utc(datetime(2026, 9, 2, 14, 3, 11), 180)
    assert result.tzinfo is not None
    assert result.utcoffset() == datetime(2026, 1, 1, tzinfo=UTC).utcoffset()


def test_server_time_keeps_the_broker_wall_clock() -> None:
    """`time_server` — часы брокера с меткой UTC, а не момент времени (SPEC.md 6.3)."""
    normalized = normalize_deal(deal(time_server="2026-09-02T14:03:11"), 180)
    assert normalized.time_server == datetime(2026, 9, 2, 14, 3, 11, tzinfo=UTC)
    assert normalized.time_utc == datetime(2026, 9, 2, 11, 3, 11, tzinfo=UTC)


@pytest.mark.parametrize(
    "convert",
    [
        pytest.param(lambda value: to_utc(value, 180), id="to_utc"),
        pytest.param(label_server_time, id="label_server_time"),
    ],
)
def test_aware_input_is_rejected(convert: Callable[[datetime], datetime]) -> None:
    """Aware-вход означает, что кто-то уже проставил зону; `.replace` переклеил бы её молча."""
    aware = datetime(2026, 9, 2, 14, 3, 11, tzinfo=UTC)
    with pytest.raises(ValueError, match=re.escape(SERVER_TIME_NOT_NAIVE)):
        convert(aware)


def test_offset_comes_from_the_batch_not_from_account_state() -> None:
    """Развилка 4: смена смещения не пересчитывает прошлое (SPEC.md 6.3).

    Одна и та же сделка, два батча с разным смещением — два разных `time_utc`. Функции
    неоткуда взять «текущее смещение счёта», потому что она его не принимает.
    """
    body = deal_body(time_server="2026-10-25T03:30:00")

    summer = normalize_batch(batch([body], offset=180)).deals[0]
    winter = normalize_batch(batch([body], offset=120)).deals[0]

    assert summer.time_utc == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert winter.time_utc == datetime(2026, 10, 25, 1, 30, tzinfo=UTC)


# --- Батч и неизвестные коды (развилка 3) -------------------------------------------


def test_raw_keeps_the_original_mt5_codes() -> None:
    """Исходное число не теряется: оно уезжает в `deals.raw` целиком."""
    normalized = normalize_deal(deal(type=99, reason=42, entry=2), 180)

    assert normalized.deal_type == "other"
    assert normalized.reason == "other"
    assert normalized.raw["type"] == 99
    assert normalized.raw["reason"] == 42
    assert normalized.raw["entry"] == 2


def test_raw_carries_money_without_float() -> None:
    """JSONB получает строки, а не float: цена и деньги обязаны пережить сериализацию."""
    normalized = normalize_deal(deal(commission="-0.35", price="1.08543"), 180)

    assert normalized.raw["commission"] == "-0.35"
    assert normalized.raw["price"] == "1.08543"
    assert normalized.commission == Decimal("-0.35")
    assert normalized.price == Decimal("1.08543")


def test_documented_other_code_sets_are_pinned_to_the_mt5_enums() -> None:
    """Литералом, а не производной от самих констант.

    `ENUM_DEAL_TYPE` — ровно 18 членов (0..17), `ENUM_DEAL_REASON` — ровно 11 (0..10).
    Всё, что не попало в маппинг §6.2, документировано и свёрнуто в 'other' осознанно.
    Набор, построенный из самой константы, зелен при любом её содержимом: лишний код тогда
    даёт ложную тревогу молча, недостающий — молчание там, где нужен сигнал.

    Полнота (последние две строки) — то, что делает набор проверяемым утверждением о MT5,
    а не списком чисел: между маппингом и документированным «прочим» не остаётся дыр.
    """
    deal_type_codes = {4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17}
    assert set(DOCUMENTED_OTHER_DEAL_TYPE_CODES) == deal_type_codes
    assert set(DOCUMENTED_OTHER_REASON_CODES) == {7, 8, 9, 10}
    assert set(DEAL_TYPE_BY_CODE) | set(DOCUMENTED_OTHER_DEAL_TYPE_CODES) == set(range(18))
    assert set(REASON_BY_CODE) | set(DOCUMENTED_OTHER_REASON_CODES) == set(range(11))


def test_documented_other_codes_are_not_reported_as_unknown() -> None:
    """Своп и комиссия приходят каждый день; репорт про них утопил бы настоящий сигнал.

    Коды перечислены литералом по той же причине: вход, собранный из проверяемой
    константы, подтверждает сам себя.
    """
    bodies = [deal_body(ticket=1, type=code, reason=0) for code in range(4, 18)]
    bodies += [deal_body(ticket=2, type=0, reason=code) for code in range(7, 11)]

    assert normalize_batch(batch(bodies)).unknown_codes == ()


def test_unknown_codes_are_counted_and_ordered() -> None:
    """Код вне перечисления MT5 — сигнал: свернули в 'other', но сказали об этом.

    Порядок вставки здесь намеренно обратен ожидаемому — и по полю, и по коду. Иначе
    сортировка ничего не значит: строка в логе плясала бы от батча к батчу, а тест этого
    не замечал.
    """
    result = normalize_batch(
        batch(
            [
                deal_body(ticket=1, type=0, reason=77),
                deal_body(ticket=2, type=99, reason=0),
                deal_body(ticket=3, type=99, reason=0),
                deal_body(ticket=4, type=88, reason=66),
                deal_body(ticket=5, type=7, reason=9),  # оба кода документированы
            ]
        )
    )

    assert result.unknown_codes == (
        UnknownCode(field="deal_type", code=88, count=1),
        UnknownCode(field="deal_type", code=99, count=2),
        UnknownCode(field="reason", code=66, count=1),
        UnknownCode(field="reason", code=77, count=1),
    )


def test_empty_batch_normalizes_to_nothing() -> None:
    result = normalize_batch(batch([]))
    assert result.deals == ()
    assert result.unknown_codes == ()


def test_batch_normalizes_every_deal_and_keeps_order() -> None:
    result = normalize_batch(
        batch([deal_body(ticket=10), deal_body(ticket=11), deal_body(ticket=12)])
    )
    assert [item.deal_ticket for item in result.deals] == [10, 11, 12]


def test_symbol_and_broker_fields_pass_through_untouched() -> None:
    """Символ нормализует S1-07; `order`/`magic` = 0 остаются нулями, а не становятся NULL."""
    source = deal(symbol="XAUUSD.pro", order=0, magic=0, comment="tp 2450")
    normalized = normalize_deal(source, 180)

    assert normalized.symbol_raw == "XAUUSD.pro"
    assert normalized.order_ticket == 0
    assert normalized.magic == 0
    assert normalized.comment == "tp 2450"


# --- Чистота: проверено, а не заявлено ----------------------------------------------

# Механизм разбора исходника живёт в `tests/purity.py` — он общий с S1-07. Здесь остаётся
# контракт, и это та часть, которую читает ревьюер: ровно то, без чего нормализатор не
# написать. Любой новый импорт делает тест красным и заставляет объяснить, зачем чистой
# функции понадобился внешний мир.
NORMALIZER_PURITY = PurityContract(
    allowed_imports=frozenset(
        {
            "__future__",
            "app.domains.ingest.schemas",
            "collections",
            "collections.abc",
            "dataclasses",
            "datetime",
            "decimal",
            "typing",
        }
    ),
    allowed_builtins=frozenset(
        {"ValueError", "dict", "frozenset", "int", "sorted", "str", "tuple"}
    ),
)


def test_normalizer_imports_nothing_impure() -> None:
    assert imported_modules(module_tree(normalizer)) <= NORMALIZER_PURITY.allowed_imports


def test_normalizer_takes_nothing_from_outside_beyond_imports_and_plain_builtins() -> None:
    """Белый список: всё, чего модуль не импортировал и не определил, обязано быть здесь."""
    tree = module_tree(normalizer)
    assert [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)], (
        "модуль обязан определять функции, иначе тест ничего не проверяет"
    )
    assert external_names(tree) <= NORMALIZER_PURITY.allowed_builtins


def test_normalizer_never_reaches_for_clock_environment_or_io() -> None:
    tree = module_tree(normalizer)
    assert leaks(tree, NORMALIZER_PURITY) == set()
    # Иначе дыру можно открыть, дописав `now` в белый список, и оба теста останутся зелёными.
    assert NORMALIZER_PURITY.allowed_builtins.isdisjoint(IMPURE_NAMES)
    assert bound_names(tree).isdisjoint(NORMALIZER_PURITY.guarded), (
        "модуль затеняет имя, на котором держится проверка"
    )


@pytest.mark.parametrize("case", sorted(IMPURE_SNIPPETS))
def test_purity_check_is_not_vacuous(case: str) -> None:
    """Проверка проверки: три известных обхода обязаны быть красными на этом контракте.

    Утверждение «функции чистые» стоит ровно столько, сколько ловит проверка. Прошлая
    версия ловила ноль из трёх и при этом выглядела строгой.
    """
    assert leaks(ast.parse(IMPURE_SNIPPETS[case]), NORMALIZER_PURITY)


@pytest.fixture
def machine_timezone(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[str], None]]:
    """Подмена зоны процесса. Восстанавливается вместе с `TZ`, иначе течёт в соседние тесты."""

    def _set(zone: str) -> None:
        monkeypatch.setenv("TZ", zone)
        time.tzset()

    yield _set
    monkeypatch.undo()
    time.tzset()


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="tzset есть только на Unix")
def test_result_does_not_depend_on_machine_timezone(
    machine_timezone: Callable[[str], None],
) -> None:
    """Зона машины не участвует: иначе один и тот же батч дал бы разное время на разных машинах."""
    machine_timezone("UTC")
    reference = normalize_batch(batch([deal_body()], offset=180)).deals[0]

    for zone in ("Asia/Tokyo", "America/Sao_Paulo", "Pacific/Kiritimati", "Europe/Moscow"):
        machine_timezone(zone)
        assert normalize_batch(batch([deal_body()], offset=180)).deals[0] == reference


def test_repeated_normalization_is_identical() -> None:
    source = batch([deal_body(ticket=1), deal_body(ticket=2, type=7, position_id=5)])
    assert normalize_batch(source) == normalize_batch(source)
