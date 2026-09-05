"""Валидация тел коллектора — SPEC.md 5.3, 5.6. Живых зависимостей не требует."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domains.accounts import service as accounts
from app.domains.collector.schemas import (
    COLLECTOR_ID_MAX_LENGTH,
    COLLECTOR_STATES,
    MAX_HEARTBEAT_ACCOUNTS,
    MESSAGE_MAX_LENGTH,
    HeartbeatRequest,
    validate_collector_id,
)

COLLECTOR = "desk-01"


def _account(**overrides: object) -> dict[str, object]:
    return {"account_id": str(uuid4()), "state": "running", **overrides}


def test_heartbeat_states_match_the_domain() -> None:
    """Множество состояний в схеме и в `apply_heartbeat` — одно.

    Разъехавшись, они дали бы состояние, которое проходит валидацию и молча ничего
    не меняет: heartbeat отвечает «принято», статус не двигается, никто не замечает.
    """
    assert set(COLLECTOR_STATES) == set(accounts.HEARTBEAT_STATES)


@pytest.mark.parametrize(
    "value", ["desk-01", "WIN-PC.local", "a", "0", "collector_1:2", "n@host", "9" * 64]
)
def test_valid_collector_ids_pass(value: str) -> None:
    assert validate_collector_id(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "-начинается-с-дефиса",
        "коллектор",  # кириллица: закрытый алфавит намеренно её не пускает
        "desk 01",
        "desk/01",
        "<b>desk</b>",
        "x" * (COLLECTOR_ID_MAX_LENGTH + 1),
    ],
)
def test_collector_id_outside_the_alphabet_is_rejected(value: str) -> None:
    """`collector_id` уезжает в `AccountResponse` на все экраны (X-21, второй канал).

    Закрытый алфавит закрывает канал целиком: разметку и произвольный текст сюда
    физически не положить.
    """
    with pytest.raises(ValidationError):
        HeartbeatRequest(collector_id=value, accounts=[])


def test_collector_id_is_trimmed() -> None:
    assert HeartbeatRequest(collector_id=" desk-01 ", accounts=[]).collector_id == COLLECTOR


def test_empty_account_list_is_a_valid_heartbeat() -> None:
    """Коллектор без счетов всё равно должен уметь сказать, что он жив."""
    assert HeartbeatRequest(collector_id=COLLECTOR, accounts=[]).accounts == []


def test_duplicate_account_in_one_batch_is_rejected() -> None:
    """«Побеждает последний» сделало бы статус функцией порядка в списке."""
    account_id = str(uuid4())
    with pytest.raises(ValidationError):
        HeartbeatRequest.model_validate(
            {
                "collector_id": COLLECTOR,
                "accounts": [
                    {"account_id": account_id, "state": "running"},
                    {"account_id": account_id, "state": "error"},
                ],
            }
        )


def test_unknown_state_is_rejected() -> None:
    with pytest.raises(ValidationError):
        HeartbeatRequest.model_validate(
            {"collector_id": COLLECTOR, "accounts": [_account(state="paused")]}
        )


def test_extra_field_is_rejected() -> None:
    """Опечатка в имени поля не должна выглядеть как «принято»."""
    with pytest.raises(ValidationError):
        HeartbeatRequest.model_validate(
            {"collector_id": COLLECTOR, "accounts": [_account(stat3="running")]}
        )


def test_too_many_accounts_are_rejected() -> None:
    with pytest.raises(ValidationError):
        HeartbeatRequest.model_validate(
            {
                "collector_id": COLLECTOR,
                "accounts": [_account() for _ in range(MAX_HEARTBEAT_ACCOUNTS + 1)],
            }
        )


def test_overlong_message_is_rejected() -> None:
    """Потолок, за которым это уже не сообщение, а транспорт для дампа."""
    with pytest.raises(ValidationError):
        HeartbeatRequest.model_validate(
            {
                "collector_id": COLLECTOR,
                "accounts": [_account(state="error", message="я" * (MESSAGE_MAX_LENGTH + 1))],
            }
        )


@pytest.mark.parametrize("value", [True, 0, -1])
def test_terminal_login_must_be_a_positive_integer(value: object) -> None:
    with pytest.raises(ValidationError):
        HeartbeatRequest.model_validate(
            {"collector_id": COLLECTOR, "accounts": [_account(terminal_login=value)]}
        )
