"""Поведение моделей батча ингеста (S1-01, SPEC.md 5.3).

Здесь проверяется то, ради чего модели существуют: что форма принимается, что деньги
доезжают до Decimal без float, что два поля времени не могут разойтись и что неверный
батч превращается в 400 с именем поля. Маршрута ещё нет (S1-04), поэтому последнее
проверяется на настоящих обработчиках ошибок приложения и временном маршруте теста.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.errors import register_error_handlers
from app.domains.ingest import schemas
from app.domains.ingest.schema_export import REPO_ROOT
from app.domains.ingest.schemas import (
    MAX_BIGINT,
    MAX_DEALS_PER_BATCH,
    TRADING_DEAL_TYPE_CODES,
    IngestDeal,
    IngestDealsBatch,
    IngestOpenPosition,
)

# Побайтная копия блока из SPEC.md 5.3, вплоть до многоточия в open_positions. Лежит
# файлом, а не строкой в коде: так её видно ревью и так её сверяет тест ниже.
SPEC_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "fixtures/ingest/spec-5.3-example.json"

# Два места, в которых пример не является документом: заглушки «uuid» и «…». Ровно эти
# два и никаких других — список сверяется тестом, поэтому правка SPEC.md сделает его
# красным и заставит вернуться сюда. Третьим здесь был `deals.0.time_msc`: в примере
# стояло 1756821791123 (2025 год) при `time_server` за 2026-й; SPEC.md v1.8 это исправил.
SPEC_EXAMPLE_DEFECTS = {
    "account_id",
    "open_positions.0.time_server",
}

ACCOUNT_ID = "0199a5c1-7d7a-7c3e-8f2a-1b2c3d4e5f60"


def spec_example(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(SPEC_EXAMPLE_PATH.read_text(encoding="utf-8"))
    body.update(overrides)
    return body


def filled_spec_example() -> dict[str, Any]:
    """Пример SPEC.md с заполненными заглушками.

    Заполняются ровно места из `SPEC_EXAMPLE_DEFECTS`; ни одно поле не подгоняется под
    модель — иначе «пример из спеки проходит» ничего бы не значило.
    """
    body = spec_example(account_id=ACCOUNT_ID)
    body["open_positions"][0]["time_server"] = "2026-09-02T09:15:00"
    return body


def locations(error: ValidationError) -> set[str]:
    return {".".join(str(part) for part in item["loc"]) for item in error.errors()}


def deal(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = filled_spec_example()["deals"][0]
    body.update(overrides)
    return body


def batch(**overrides: Any) -> dict[str, Any]:
    body = filled_spec_example()
    body.update(overrides)
    return body


# --- пример из спеки -------------------------------------------------------------


def test_fixture_is_the_spec_block_byte_for_byte() -> None:
    """Иначе «пример из спеки проходит» означало бы «проходит наша копия примера».

    Правка блока в SPEC.md делает этот тест красным — и это единственный способ узнать,
    что контракт в документе поехал относительно контракта в коде.
    """
    spec = (REPO_ROOT / "SPEC.md").read_text(encoding="utf-8")
    section = spec.split("### 5.3 ingest", 1)[1]
    block = re.search(r"```json\n(.*?)```", section, re.DOTALL)

    assert block is not None
    assert block.group(1) == SPEC_EXAMPLE_PATH.read_text(encoding="utf-8")


def test_spec_example_fails_only_on_its_own_placeholders() -> None:
    """Дословный пример SPEC.md 5.3 документом не является: в нём заглушки."""
    with pytest.raises(ValidationError) as error:
        IngestDealsBatch.model_validate(spec_example())
    assert locations(error.value) == SPEC_EXAMPLE_DEFECTS


def test_spec_example_passes_once_placeholders_are_filled() -> None:
    """Заглушки заполнены — остальной пример проходит без единой правки под модель."""
    parsed = IngestDealsBatch.model_validate(filled_spec_example())

    assert parsed.source == "collector"
    assert parsed.server_utc_offset_minutes == 180
    assert parsed.account_info.margin_mode == "hedging"
    assert len(parsed.deals) == 1
    assert len(parsed.open_positions) == 1


def test_spec_example_survives_json_bytes() -> None:
    """Тот же путь, которым тело придёт из HTTP: разбор из байтов, а не из dict."""
    parsed = IngestDealsBatch.model_validate_json(json.dumps(filled_spec_example()))

    assert parsed.deals[0].price == Decimal("1.08543")


# --- точность --------------------------------------------------------------------


def test_json_numbers_reach_decimal_without_float_drift() -> None:
    """Число JSON доезжает до Decimal ровно тем значением, которое записано в тексте."""
    parsed = IngestDeal.model_validate_json(
        json.dumps(deal(volume=0.1, price=0.2, commission=-0.35, profit=0.1))
    )

    assert parsed.volume == Decimal("0.1")
    assert parsed.price == Decimal("0.2")
    assert parsed.commission == Decimal("-0.35")
    # Ради этого всё и затевалось: в float сумма трёх десятых даёт 0.30000000000000004,
    # и на сотнях сделок S1-12 не сойдётся в 0,00.
    assert parsed.volume + parsed.price == Decimal("0.3")
    assert sum([parsed.profit] * 3, Decimal(0)) == Decimal("0.3")


def test_strings_are_accepted_for_money_and_volume() -> None:
    """Строка — путь без float вообще; коллектор может слать её ради побитовой точности."""
    parsed = IngestDeal.model_validate(deal(volume="0.10", price="1.08543", swap="-0.07"))

    assert parsed.volume == Decimal("0.10")
    assert parsed.price == Decimal("1.08543")
    assert parsed.swap == Decimal("-0.07")


def test_money_string_keeps_more_digits_than_float_can() -> None:
    """Строкой доезжает и то, что через float уже не проходит."""
    parsed = IngestDeal.model_validate(deal(price="1.234567890123456789"))

    assert parsed.price == Decimal("1.234567890123456789")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "nan"])
def test_not_a_number_is_rejected(value: str) -> None:
    """`Decimal("NaN")` — валидный Decimal и яд для любой суммы."""
    with pytest.raises(ValidationError) as error:
        IngestDeal.model_validate(deal(profit=value))
    assert "profit" in locations(error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("profit", "10000000000000000"),  # не влезает в numeric(18,2)
        ("profit", "-10000000000000000"),
        ("volume", "10000000000"),  # не влезает в numeric(18,8)
        ("volume", "-0.01"),  # объём отрицательным не бывает
        ("price", "-1"),
    ],
)
def test_values_outside_column_bounds_are_rejected(field: str, value: str) -> None:
    """Отказ на границе, а не пятисотка из Postgres на вставке."""
    with pytest.raises(ValidationError) as error:
        IngestDeal.model_validate(deal(**{field: value}))
    assert field in locations(error.value)


@pytest.mark.parametrize("field", ["ticket", "order", "position_id", "magic"])
@pytest.mark.parametrize("value", [2**63, 10**30])
def test_integers_outside_bigint_are_rejected(field: str, value: int) -> None:
    """Целые едут в bigint (`models.py`), и знаковый предел у него тот же, что здесь.

    Без верхней границы такое значение проходило бы валидацию и падало на вставке:
    пятисотка вместо 400 с именем поля — ровно то, от чего берегут MONEY_LIMIT и
    QUANTITY_LIMIT. Довод «производитель один и он наш» тут не работает: контракт сам
    объявляет `source: "ea" | "csv"`, то есть отправителей, которых мы не писали.
    """
    with pytest.raises(ValidationError) as error:
        IngestDeal.model_validate(deal(**{field: value}))
    assert field in locations(error.value)


def test_the_largest_bigint_is_still_a_valid_ticket() -> None:
    """Граница включающая: предельное значение колонки — валидный тикет, а не отказ."""
    parsed = IngestDeal.model_validate(deal(ticket=MAX_BIGINT))

    assert parsed.ticket == MAX_BIGINT


def test_open_position_id_outside_bigint_is_rejected() -> None:
    """`positions.position_id` — та же bigint-колонка, что у сделки."""
    body = filled_spec_example()["open_positions"][0]
    body["position_id"] = 2**63

    with pytest.raises(ValidationError) as error:
        IngestOpenPosition.model_validate(body)
    assert "position_id" in locations(error.value)


# --- время -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "2026-09-02T14:03:11Z",
        "2026-09-02T14:03:11+03:00",
        "2026-09-02T14:03:11-00:00",
        "2026-09-02 14:03:11",
        "2026-09-02T14:03",
        "02.09.2026 14:03:11",
        "1788357791",
        "2026-13-45T14:03:11",
    ],
)
def test_server_time_accepts_only_naive_iso(value: str) -> None:
    """Суффикс зоны отвергается, а не отбрасывается: угадывать смысл здесь нельзя."""
    with pytest.raises(ValidationError) as error:
        IngestDeal.model_validate(deal(time_server=value, time_msc=1788357791123))
    assert "time_server" in locations(error.value)


def test_server_time_accepts_fractional_seconds() -> None:
    parsed = IngestDeal.model_validate(
        deal(time_server="2026-09-02T14:03:11.123456", time_msc=1788357791123)
    )

    assert parsed.time_server == datetime(2026, 9, 2, 14, 3, 11, 123456)
    assert parsed.time_server.tzinfo is None


def test_aware_datetime_object_is_rejected() -> None:
    """Тот же запрет и для питоновского пути: модель строят и тесты, и S1-02."""
    with pytest.raises(ValidationError) as error:
        IngestDeal.model_validate(
            deal(time_server=datetime(2026, 9, 2, 14, 3, 11, tzinfo=UTC), time_msc=1788357791123)
        )
    assert "time_server" in locations(error.value)


def test_time_msc_must_agree_with_time_server() -> None:
    """Два источника правды про один момент, разошедшиеся на год.

    Ровно это и стояло в примере SPEC.md 5.3 до v1.8; проверка держит число, чтобы
    найденный дефект остался пойманным, а не только исправленным.
    """
    with pytest.raises(ValidationError) as error:
        IngestDeal.model_validate(deal(time_server="2026-09-02T14:03:11", time_msc=1756821791123))
    assert "time_msc" in locations(error.value)


@pytest.mark.parametrize("time_msc", [1788357791000, 1788357791123, 1788357791999])
def test_time_msc_agrees_within_the_same_second(time_msc: int) -> None:
    """MT5 отдаёт `time` как целые секунды того же события: сходимся по секунде."""
    parsed = IngestDeal.model_validate(deal(time_server="2026-09-02T14:03:11", time_msc=time_msc))

    assert parsed.time_msc == time_msc


@pytest.mark.parametrize("time_msc", [1788357790999, 1788357792000])
def test_time_msc_one_second_off_is_rejected(time_msc: int) -> None:
    with pytest.raises(ValidationError) as error:
        IngestDeal.model_validate(deal(time_server="2026-09-02T14:03:11", time_msc=time_msc))
    assert "time_msc" in locations(error.value)


@pytest.mark.parametrize("offset", [-721, 841, 100, 7, 1])
def test_offset_outside_range_or_step_is_rejected(offset: int) -> None:
    with pytest.raises(ValidationError) as error:
        IngestDealsBatch.model_validate(batch(server_utc_offset_minutes=offset))
    assert "server_utc_offset_minutes" in locations(error.value)


@pytest.mark.parametrize("offset", [-720, -180, 0, 45, 180, 840])
def test_offset_of_a_real_timezone_is_accepted(offset: int) -> None:
    parsed = IngestDealsBatch.model_validate(batch(server_utc_offset_minutes=offset))

    assert parsed.server_utc_offset_minutes == offset


# --- форма батча -----------------------------------------------------------------


def test_unknown_field_is_rejected() -> None:
    """`extra="forbid"`: опечатка коллектора не должна тихо обнулять деньги."""
    with pytest.raises(ValidationError) as error:
        IngestDeal.model_validate(deal(commision="-0.35"))
    assert "commision" in locations(error.value)


def test_unknown_field_in_batch_is_rejected() -> None:
    with pytest.raises(ValidationError) as error:
        IngestDealsBatch.model_validate(batch(collector_id="win-1"))
    assert "collector_id" in locations(error.value)


@pytest.mark.parametrize("field", ["deals", "open_positions", "account_info", "account_id"])
def test_required_fields_cannot_be_omitted(field: str) -> None:
    """Пустой список и отсутствие поля — разные утверждения (SPEC.md 5.3, пункты 4-5)."""
    body = filled_spec_example()
    del body[field]

    with pytest.raises(ValidationError) as error:
        IngestDealsBatch.model_validate(body)
    assert field in locations(error.value)


def test_empty_lists_are_a_valid_batch() -> None:
    """Окно без новых сделок и счёт без открытых позиций — обычный батч."""
    parsed = IngestDealsBatch.model_validate(batch(deals=[], open_positions=[]))

    assert parsed.deals == []
    assert parsed.open_positions == []


def test_manual_source_is_not_an_ingest_source() -> None:
    """Ручные сделки заводятся через журнал и помечаются `is_manual` (SPEC.md 5.4)."""
    with pytest.raises(ValidationError) as error:
        IngestDealsBatch.model_validate(batch(source="manual"))
    assert "source" in locations(error.value)


@pytest.mark.parametrize("entry", [-1, 4, 99])
def test_entry_outside_the_mt5_enum_is_rejected(entry: int) -> None:
    """У `entry` нет запасного значения в SPEC.md 6.2, а колонка NOT NULL."""
    with pytest.raises(ValidationError) as error:
        IngestDeal.model_validate(deal(entry=entry))
    assert "entry" in locations(error.value)


@pytest.mark.parametrize("deal_type", [0, 1, 2, 3, 17, 99])
def test_unknown_deal_type_is_accepted_and_left_to_the_normalizer(deal_type: int) -> None:
    """SPEC.md 6.2: неизвестный `DEAL_TYPE_*` становится 'other', а не ошибкой ингеста."""
    parsed = IngestDeal.model_validate(deal(type=deal_type))

    assert parsed.type == deal_type


def test_open_position_type_is_limited_to_buy_and_sell() -> None:
    """У открытой позиции другой enum, чем у сделки: код вне 0/1 — перепутанные константы."""
    body = filled_spec_example()["open_positions"][0]
    body["type"] = 2

    with pytest.raises(ValidationError) as error:
        IngestOpenPosition.model_validate(body)
    assert "type" in locations(error.value)


@pytest.mark.parametrize("symbol", ["", " ", "EUR USD", "x" * 65])
def test_symbol_must_be_a_single_word(symbol: str) -> None:
    """Сделка примера — торговая (`type = 0`), поэтому пустой символ ей по-прежнему нельзя."""
    with pytest.raises(ValidationError) as error:
        IngestDeal.model_validate(deal(symbol=symbol))
    assert "symbol" in locations(error.value)


# --- X-44: пустой символ у неторговой операции ------------------------------------

# Депозит из настоящей выгрузки (7 сентября 2026), обезличенный: в исходном комментарии
# стоял внутренний номер платежа, здесь от него остался только тип операции.
DEPOSIT: dict[str, Any] = {
    "ticket": 104238311,
    "order": 0,
    "position_id": 0,
    "type": 2,
    "symbol": "",
    "entry": 0,
    "reason": 0,
    "volume": "0",
    "price": "0",
    "profit": "615.46",
    "commission": "0",
    "swap": "0",
    "fee": "0",
    "time_server": "2025-11-26T06:13:09",
    "time_msc": 1764137589234,
    "comment": "Deposit",
    "magic": 0,
}


def test_deposit_without_a_symbol_is_accepted() -> None:
    """Ровно та сделка, что отвергала весь батч у каждого, кто пополнял счёт (X-44)."""
    parsed = IngestDeal.model_validate(DEPOSIT)

    assert parsed.symbol == ""
    assert parsed.type == 2


@pytest.mark.parametrize("deal_type", [2, 3, 6, 12, 99])
def test_non_trading_deal_may_come_without_a_symbol(deal_type: int) -> None:
    """Инструмента нет ни у пополнения, ни у кредита, ни у любого начисления."""
    parsed = IngestDeal.model_validate(deal(type=deal_type, symbol=""))

    assert parsed.symbol == ""


@pytest.mark.parametrize("deal_type", sorted(TRADING_DEAL_TYPE_CODES))
def test_trading_deal_without_a_symbol_is_still_rejected(deal_type: int) -> None:
    """Послабление не должно пропустить сделку, про которую неизвестно, чем торговали."""
    with pytest.raises(ValidationError) as error:
        IngestDeal.model_validate(deal(type=deal_type, symbol=""))

    assert "symbol" in locations(error.value)


def test_the_trading_rule_is_what_rejects_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Мутация: снять правило — и сделка выше начинает проходить.

    Без этого «торговая без инструмента отвергается» доказывало бы только то, что её
    отвергает *что-то* — например, уцелевший `min_length`, который X-44 как раз снял.
    """
    monkeypatch.setattr(schemas, "TRADING_DEAL_TYPE_CODES", frozenset())

    parsed = IngestDeal.model_validate(deal(type=0, symbol=""))

    assert parsed.symbol == ""


def test_open_position_still_requires_a_symbol() -> None:
    """У открытой позиции инструмент есть всегда: послабление её не касается."""
    body = filled_spec_example()["open_positions"][0]
    body["symbol"] = ""

    with pytest.raises(ValidationError) as error:
        IngestOpenPosition.model_validate(body)
    assert "symbol" in locations(error.value)


def test_non_usd_currency_is_accepted_by_the_boundary() -> None:
    """Не-USD разбирает домен (S1-06, `needs_attention`), а не валидация формы."""
    body = filled_spec_example()
    body["account_info"]["currency"] = "EUR"

    parsed = IngestDealsBatch.model_validate(body)

    assert parsed.account_info.currency == "EUR"


def test_batch_over_the_limit_is_not_a_validation_error() -> None:
    """Развилка лимита: 5 001 сделка проходит валидацию, чтобы S1-04 ответил 413.

    Поставь `maxItems` в модель — и тот же батч стал бы 400 `validation_error`, а
    SPEC.md 5.3 требует 413. Ограничение живёт в маршруте и опирается на эту константу.
    """
    one = filled_spec_example()["deals"][0]
    oversized = batch(
        deals=[dict(one, ticket=one["ticket"] + index) for index in range(MAX_DEALS_PER_BATCH + 1)]
    )

    parsed = IngestDealsBatch.model_validate(oversized)

    assert len(parsed.deals) == MAX_DEALS_PER_BATCH + 1


# --- DoD: невалидный батч → 400 с указанием поля ---------------------------------


@pytest.fixture
def boundary_app() -> FastAPI:
    """Приложение из настоящих обработчиков ошибок и временного маршрута.

    Маршрут `POST /ingest/deals` — это S1-04, и половинчатой его версии здесь быть не
    должно: S1-04 её всё равно перепишет. А доказать DoD «невалидный батч → 400 с
    указанием поля» без единого маршрута нельзя — 400 рождается не в модели, а в
    `validation_error_handler`. Маршрут живёт только внутри теста и ничего не публикует.
    """
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/probe")
    async def probe(payload: IngestDealsBatch) -> dict[str, int]:
        return {"received": len(payload.deals)}

    return app


@pytest.fixture
async def client(boundary_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=boundary_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_valid_batch_passes_the_boundary(client: AsyncClient) -> None:
    response = await client.post("/probe", json=filled_spec_example())

    assert response.status_code == 200
    assert response.json() == {"received": 1}


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        ({"server_utc_offset_minutes": 7}, "body.server_utc_offset_minutes"),
        ({"source": "manual"}, "body.source"),
        ({"account_id": "uuid"}, "body.account_id"),
    ],
)
async def test_invalid_batch_is_400_naming_the_field(
    client: AsyncClient, mutation: dict[str, Any], field: str
) -> None:
    """DoD S1-01: 400, код из SPEC.md 5.1 и путь до поля в `details.fields`."""
    response = await client.post("/probe", json=batch(**mutation))

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert field in body["error"]["details"]["fields"]


async def test_invalid_deal_points_at_its_index(client: AsyncClient) -> None:
    """В батче на тысячи сделок «ошибка в deals» бесполезна: нужен индекс."""
    body = filled_spec_example()
    body["deals"].append(dict(body["deals"][0], ticket=2, entry=9))

    response = await client.post("/probe", json=body)

    assert response.status_code == 400
    assert "body.deals.1.entry" in response.json()["error"]["details"]["fields"]


async def test_batch_with_a_deposit_passes_the_boundary(client: AsyncClient) -> None:
    """Смысл X-44 целиком: одна неторговая сделка больше не отвергает весь батч."""
    body = filled_spec_example()
    body["deals"].append(DEPOSIT)

    response = await client.post("/probe", json=body)

    assert response.status_code == 200
    assert response.json() == {"received": 2}


async def test_batch_with_a_symbolless_trade_is_400_naming_the_symbol(client: AsyncClient) -> None:
    """А торговая сделка без инструмента — по-прежнему 400, и видно, где именно."""
    body = filled_spec_example()
    body["deals"].append(dict(DEPOSIT, ticket=DEPOSIT["ticket"] + 1, type=0))

    response = await client.post("/probe", json=body)

    assert response.status_code == 400
    assert "body.deals.1.symbol" in response.json()["error"]["details"]["fields"]


async def test_validation_error_does_not_echo_the_batch(client: AsyncClient) -> None:
    """Ответ несёт имя поля и причину, но не присланные значения (см. `errors.py`)."""
    response = await client.post("/probe", json=batch(source="secret-looking-value"))

    assert "secret-looking-value" not in response.text
