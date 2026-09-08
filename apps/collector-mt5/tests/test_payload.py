"""Сборка батча против опубликованного контракта `S1-01`.

Главный тест файла — `test_batch_passes_the_published_json_schema`: он проверяет то, что
иначе проверил бы только живой сервер. Схема лежит в
`packages/shared-schemas/ingest-deals.schema.json` и генерируется из pydantic-моделей
api, то есть это ровно та форма, которую граница примет.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from collector import payload
from tests.conftest import ACCOUNT_ID, FakeAccountInfo, FakeDeal, FakePosition

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "packages" / "shared-schemas" / "ingest-deals.schema.json"
)


def _batch(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "account_id": ACCOUNT_ID,
        "server_utc_offset_minutes": 120,
        "account_info": FakeAccountInfo(),
        "deals": [FakeDeal()],
        "open_positions": [FakePosition()],
    }
    defaults.update(overrides)
    return payload.build_batch(**defaults)


# --------------------------------------------------------------------------------------
# Контракт целиком
# --------------------------------------------------------------------------------------


def test_batch_passes_the_published_json_schema() -> None:
    """Единственная проверка контракта, доступная без сервера.

    `jsonschema` живёт в dev-зависимостях api и стоит в том же venv. Своей зависимостью
    коллектора он не становится: SPEC.md 2.3 его коллектору не разрешает.
    """
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(_batch(), schema)


def test_deposit_without_a_symbol_passes_the_schema() -> None:
    """Неторговая операция приходит с пустым символом — X-44, 504-я сделка выгрузки."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    deposit = FakeDeal(type=2, symbol="", order=0, position_id=0, profit=500.0, comment="Deposit")
    jsonschema.validate(_batch(deals=[deposit]), schema)


def test_batch_carries_every_required_field() -> None:
    batch = _batch()
    assert set(batch) == {
        "account_id",
        "source",
        "server_utc_offset_minutes",
        "account_info",
        "deals",
        "open_positions",
    }
    assert batch["source"] == "collector"


def test_empty_batch_is_a_valid_message() -> None:
    """Батч без сделок — законное «жив, открытых позиций нет»: на нём держится last_sync_at."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(_batch(deals=[], open_positions=[]), schema)


# --------------------------------------------------------------------------------------
# Время
# --------------------------------------------------------------------------------------


def test_terminal_time_is_treated_as_broker_clock_not_utc() -> None:
    """SPEC.md 6.3: `fromtimestamp(t, tz=UTC)` — «фальшивый UTC», равный часам брокера.

    Если однажды кто-то решит «привести к UTC» здесь, время уедет на смещение сервера, а
    сделка — в чужой торговый день. Тест держит именно это.
    """
    assert payload.server_time_text(1_788_357_791) == "2026-09-02T14:03:11"


def test_time_server_matches_time_msc_to_the_second() -> None:
    """Граница сверяет два поля между собой и отвергает батч целиком при расхождении."""
    body = payload.deal_payload(FakeDeal(time=1_788_357_791, time_msc=1_788_357_791_999))
    assert body["time_server"] == "2026-09-02T14:03:11"
    assert body["time_msc"] // 1000 == 1_788_357_791


def test_deal_with_disagreeing_time_fields_is_not_sent() -> None:
    reason = payload.unsendable_reason(FakeDeal(time=1_788_357_791, time_msc=1_000))
    assert reason is not None
    assert "расходятся" in reason


@pytest.mark.parametrize("moment", [0, -1])
def test_deal_without_a_time_is_not_sent(moment: int) -> None:
    assert payload.unsendable_reason(FakeDeal(time=moment, time_msc=moment * 1000)) is not None


# --------------------------------------------------------------------------------------
# Числа
# --------------------------------------------------------------------------------------


def test_float64_noise_travels_untouched() -> None:
    """Шум брокера (`-1.6099999999999999`) округляет сервер, а не коллектор.

    Округление в двух местах — это два разных решения об одном числе, и однажды они
    разойдутся. Решение принято в S1-03 (поштучно, до сложения), здесь его нет.
    """
    body = payload.deal_payload(FakeDeal(commission=-1.6099999999999999))
    assert body["commission"] == "-1.6099999999999999"


def test_small_numbers_do_not_leave_as_exponent() -> None:
    """Шаблон схемы экспоненты не знает: `1e-07` отверг бы весь батч."""
    assert payload.decimal_text(1e-07) == "0.0000001"
    assert "e" not in payload.decimal_text(0.00000012)


def test_money_arrives_as_a_string() -> None:
    """Строка доезжает до Decimal вообще без float — так решено в контракте S1-01."""
    body = payload.deal_payload(FakeDeal(volume=0.1, price=1.08543))
    assert body["volume"] == "0.1"
    assert body["price"] == "1.08543"
    assert isinstance(body["profit"], str)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_numbers_are_refused_loudly(value: float) -> None:
    with pytest.raises(payload.UnsendableDealError):
        payload.decimal_text(value)


def test_deal_with_a_negative_volume_is_not_sent() -> None:
    reason = payload.unsendable_reason(FakeDeal(volume=-0.1))
    assert reason is not None
    assert "volume" in reason


def test_amount_beyond_the_column_is_not_sent() -> None:
    reason = payload.unsendable_reason(FakeDeal(profit=1e17))
    assert reason is not None
    assert "не помещается" in reason


def test_decimal_passes_through_without_float() -> None:
    assert payload.decimal_text(Decimal("-1.61")) == "-1.61"


# --------------------------------------------------------------------------------------
# Символы и комментарии
# --------------------------------------------------------------------------------------


def test_symbol_travels_as_the_broker_wrote_it() -> None:
    """Нормализация символов живёт на сервере (S1-07). Коллектор в имя не лезет."""
    assert payload.deal_payload(FakeDeal(symbol="$$US30"))["symbol"] == "$$US30"
    assert payload.deal_payload(FakeDeal(symbol="EURUSD.m"))["symbol"] == "EURUSD.m"


def test_symbol_with_a_space_is_not_sent() -> None:
    """Шаблон `^\\S*$`: один пробел в имени отверг бы весь батч из 5000 сделок."""
    reason = payload.unsendable_reason(FakeDeal(symbol="EUR USD"))
    assert reason is not None
    assert "пробелы" in reason


def test_trading_deal_without_a_symbol_is_not_sent() -> None:
    assert payload.unsendable_reason(FakeDeal(type=0, symbol="")) is not None


def test_non_trading_deal_without_a_symbol_is_fine() -> None:
    """Депозит инструмента не имеет — X-44 закрыт именно этим послаблением."""
    assert payload.unsendable_reason(FakeDeal(type=2, symbol="", position_id=0)) is None


def test_control_characters_in_a_comment_are_repaired_not_rejected() -> None:
    """Ремонт формы, а не смысла: байт, который никто не читает, не стоит батча."""
    assert payload.clean_comment("Limit\x00Sell[sl]") == "LimitSell[sl]"


def test_long_comment_is_trimmed_to_the_contract() -> None:
    assert len(payload.clean_comment("x" * 400)) == payload.MAX_COMMENT_LENGTH


# --------------------------------------------------------------------------------------
# Отбраковка
# --------------------------------------------------------------------------------------


def test_one_bad_deal_does_not_take_the_batch_down_with_it() -> None:
    """Цена решения названа: сделка теряется, но синхронизация счёта продолжается."""
    good, bad = FakeDeal(ticket=1), FakeDeal(ticket=2, symbol="EUR USD")
    sendable, rejected = payload.split_sendable([good, bad])
    assert [deal.ticket for deal in sendable] == [1]
    assert [item.ticket for item in rejected] == [2]
    assert rejected[0].reason


def test_a_clean_window_rejects_nothing() -> None:
    sendable, rejected = payload.split_sendable([FakeDeal(ticket=n) for n in range(5)])
    assert len(sendable) == 5
    assert rejected == []


def test_entry_outside_the_documented_range_is_not_sent() -> None:
    """Допущение 9 `docs/mt5-assumptions.md`: entry вне 0..3 роняет весь батч на границе."""
    reason = payload.unsendable_reason(FakeDeal(entry=7))
    assert reason is not None
    assert "entry" in reason


# --------------------------------------------------------------------------------------
# Счёт и открытые позиции
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(("code", "name"), [(0, "netting"), (1, "exchange"), (2, "hedging")])
def test_margin_mode_maps_by_the_spec(code: int, name: str) -> None:
    assert payload.margin_mode_name(code) == name


def test_unknown_margin_mode_is_refused_not_guessed() -> None:
    with pytest.raises(ValueError, match="неизвестный режим"):
        payload.margin_mode_name(9)


def test_open_position_takes_its_id_from_identifier() -> None:
    """У `positions_get()` идентификатор позиции — `identifier`, а не `ticket`."""
    body = payload.open_position_payload(FakePosition(identifier=777))
    assert body["position_id"] == 777


def test_account_currency_is_normalised_for_the_contract_pattern() -> None:
    body = payload.account_info_payload(FakeAccountInfo(currency=" usd "))
    assert body["currency"] == "USD"
