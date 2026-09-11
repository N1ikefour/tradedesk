"""HTTP-клиент против подставного транспорта: SPEC.md 5.1, 5.3, 5.6.

Сервер здесь ненастоящий, но форма ответов взята из моделей api дословно, а формат
ошибки — из SPEC.md 5.1. Что проверить так нельзя (настоящий токен, настоящий счёт),
названо в итоге задачи.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from collector import api_client, logging_setup
from collector.api_client import ApiClient, ApiError
from collector.config import CollectorSettings
from tests.conftest import ACCOUNT_ID, COLLECTOR_ID, TOKEN

ASSIGNMENT_BODY: dict[str, Any] = {
    "items": [
        {
            "account_id": ACCOUNT_ID,
            "server": "E-Global-Real",
            "login": 1234567,
            "password": "investor-secret",
            "sync_requested_at": None,
            "last_sync_at": "2026-09-02T14:03:11Z",
            "status": "connected",
        }
    ]
}

INGEST_BODY: dict[str, Any] = {
    "received": 10,
    "inserted": 7,
    "duplicates": 3,
    "positions_rebuilt": 2,
    "sync_run_id": "0192f1d4-2c6a-7c3f-9d1e-000000000001",
}


def _client(settings: CollectorSettings, handler: Any, *, budget: float = 0.3) -> ApiClient:
    """Клиент на подставном транспорте. Бюджет ретраев ужат: тест не имеет права спать."""
    transport = httpx.MockTransport(handler)
    return ApiClient(
        settings,
        client=httpx.Client(
            base_url=settings.api_base_url,
            transport=transport,
            headers={"Authorization": f"Bearer {TOKEN}"},
        ),
        retry_budget_seconds=budget,
        retry_max_wait_seconds=0.02,
    )


# --------------------------------------------------------------------------------------
# Assignments
# --------------------------------------------------------------------------------------


def test_assignments_are_read_from_the_items_envelope(settings: CollectorSettings) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=ASSIGNMENT_BODY)

    with _client(settings, handler) as api:
        items = api.assignments(COLLECTOR_ID)

    expected = f"/api/v1/internal/collector/assignments?collector_id={COLLECTOR_ID}"
    assert seen["url"].endswith(expected)
    assert seen["auth"] == f"Bearer {TOKEN}"
    assert items[0].login == 1234567
    assert items[0].last_sync_at == datetime(2026, 9, 2, 14, 3, 11, tzinfo=UTC)


def test_the_password_is_not_read_at_all(settings: CollectorSettings) -> None:
    """T-07: коллектор в терминал не входит, и пароль ему больше не нужен.

    Ответ в фикстуре — от сервера, который пароль ещё отдаёт. Такой сервер существует: на
    Windows коллектор обновляют руками (`run-collector.bat`), и установка, где он новее
    сервера, — обычное дело. Незнакомое поле обязано быть **не прочитано**, а не прочитано
    и спрятано: значение, не попавшее ни в одну переменную, не попадёт ни в лог, ни в кадр
    стека, ни в текст ошибки, — и защищать его отдельным `repr=False` не нужно.
    """
    with _client(settings, lambda _r: httpx.Response(200, json=ASSIGNMENT_BODY)) as api:
        assignment = api.assignments(COLLECTOR_ID)[0]
    assert not hasattr(assignment, "password")
    assert "investor-secret" not in repr(assignment)


def test_an_assignment_without_a_password_field_still_works(settings: CollectorSettings) -> None:
    """Так отвечает сегодняшний сервер (`T-07`): поля `password` в ответе нет вовсе."""
    body = json.loads(json.dumps(ASSIGNMENT_BODY))
    del body["items"][0]["password"]
    with _client(settings, lambda _r: httpx.Response(200, json=body)) as api:
        assignment = api.assignments(COLLECTOR_ID)[0]
    assert assignment.login == 1234567
    assert assignment.server == "E-Global-Real"


def test_broken_assignment_error_does_not_leak_the_payload(settings: CollectorSettings) -> None:
    """Текст исключения не цитирует тело задания, чем бы сервер его ни наполнил."""
    body = {"items": [{"account_id": ACCOUNT_ID, "password": "investor-secret"}]}
    with (
        _client(settings, lambda _r: httpx.Response(200, json=body)) as api,
        pytest.raises(ApiError) as error,
    ):
        api.assignments(COLLECTOR_ID)
    assert "investor-secret" not in str(error.value)


def test_bare_array_instead_of_the_envelope_is_refused(settings: CollectorSettings) -> None:
    with _client(settings, lambda _r: httpx.Response(200, json=[])) as api, pytest.raises(ApiError):
        api.assignments(COLLECTOR_ID)


def test_a_time_without_a_zone_is_refused_instead_of_being_guessed(
    settings: CollectorSettings,
) -> None:
    """Наивное время отсюда уехало бы в `sync.terminal_bounds`, а там `_naive` считает его
    локальным временем машины — то есть окно сместилось бы на часовой пояс пользователя.

    Сегодня от этого спасает контракт api (`SPEC.md` §5.1 требует `Z`), но в самом
    коллекторе это не заперто ничем, а цена — молча недобранные сделки у края окна.
    """
    body = json.loads(json.dumps(ASSIGNMENT_BODY))
    body["items"][0]["last_sync_at"] = "2026-09-02T14:03:11"
    with (
        _client(settings, lambda _r: httpx.Response(200, json=body)) as api,
        pytest.raises(ApiError),
    ):
        api.assignments(COLLECTOR_ID)


def test_the_password_never_becomes_a_secret_the_collector_holds(
    settings: CollectorSettings,
) -> None:
    """Раньше пароль вносился в скраб логов, потому что жил в процессе. Теперь не живёт.

    Реестр скраба остаётся пустым от пароля не потому, что о нём забыли, а потому, что
    коллектор его не читает: скрывать нечего.
    """
    with _client(settings, lambda _r: httpx.Response(200, json=ASSIGNMENT_BODY)) as api:
        api.assignments(COLLECTOR_ID)
    assert "investor-secret" not in logging_setup.known_secrets()


# --------------------------------------------------------------------------------------
# Прокси — X-68
# --------------------------------------------------------------------------------------


def test_the_client_ignores_the_system_proxy(settings: CollectorSettings, monkeypatch: Any) -> None:
    """X-68: VPN на машине трейдера прописывает себя системным прокси Windows.

    Коллектор ходит только на адрес своей установки TradeDesk, и запрос на
    `http://localhost:8000` через туннель возвращался у первого пользователя `502 Bad
    Gateway` — симптом, уводящий к «сервер сломался». Снять `trust_env=False` — и тест
    покраснеет: httpx подберёт прокси из окружения при создании клиента.
    """
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:12345")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:12345")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:12345")
    with ApiClient(settings) as api:
        client = api._client
        assert client.trust_env is False
        assert client._mounts == {}


# --------------------------------------------------------------------------------------
# Батч сделок
# --------------------------------------------------------------------------------------


def test_ingest_response_is_read_field_by_field(settings: CollectorSettings) -> None:
    with _client(settings, lambda _r: httpx.Response(200, json=INGEST_BODY)) as api:
        result = api.send_deals({"deals": []})
    assert (result.received, result.inserted, result.duplicates) == (10, 7, 3)
    assert result.positions_rebuilt == 2


def test_batch_goes_to_the_right_route(settings: CollectorSettings) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=INGEST_BODY)

    with _client(settings, handler) as api:
        api.send_deals({"account_id": ACCOUNT_ID, "deals": []})

    assert seen["path"] == "/api/v1/ingest/deals"
    assert seen["body"]["account_id"] == ACCOUNT_ID


# --------------------------------------------------------------------------------------
# Ошибки и ретраи
# --------------------------------------------------------------------------------------


def test_domain_error_arrives_as_the_server_worded_it(settings: CollectorSettings) -> None:
    """Формат SPEC.md 5.1: человеку показывается `message`, а не HTTP-код."""
    body = {"error": {"code": "account_not_found", "message": "Счёт не найден", "details": {}}}
    with (
        _client(settings, lambda _r: httpx.Response(404, json=body)) as api,
        pytest.raises(ApiError) as error,
    ):
        api.send_deals({})
    assert error.value.code == "account_not_found"
    assert error.value.message == "Счёт не найден"
    assert error.value.status == 404


def test_html_from_a_proxy_still_produces_a_readable_error(settings: CollectorSettings) -> None:
    with (
        _client(settings, lambda _r: httpx.Response(502, text="<html>bad gateway")) as api,
        pytest.raises(ApiError) as error,
    ):
        api.send_deals({})
    assert "502" in str(error.value)


def test_a_wrong_token_is_not_retried(settings: CollectorSettings) -> None:
    """401 ретраем не чинится: повторы только спрятали бы причину за таймаутами."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            401, json={"error": {"code": "unauthorized", "message": "Требуется токен"}}
        )

    with _client(settings, handler) as api, pytest.raises(ApiError):
        api.heartbeat(COLLECTOR_ID, [])
    assert len(calls) == 1


def test_a_too_large_batch_is_not_retried(settings: CollectorSettings) -> None:
    """413 — про объём, а не про сеть: повтор того же тела даст тот же ответ."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = {"error": {"code": "payload_too_large", "message": "Много"}}
        return httpx.Response(413, json=body)

    with _client(settings, handler) as api, pytest.raises(ApiError):
        api.send_deals({})
    assert len(calls) == 1


def test_a_temporary_outage_is_retried_and_then_succeeds(settings: CollectorSettings) -> None:
    responses = [httpx.Response(503), httpx.Response(200, json=INGEST_BODY)]

    def handler(_request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    with _client(settings, handler) as api:
        assert api.send_deals({}).inserted == 7
    assert responses == []


def test_retries_have_a_ceiling(settings: CollectorSettings) -> None:
    """Недоступный API не имеет права превратиться в бесконечный цикл (роль collector)."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("connection refused")

    with _client(settings, handler) as api, pytest.raises(ApiError) as error:
        api.send_deals({})
    assert "localhost:8000" in str(error.value)
    assert 1 < len(calls) < 50


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_statuses_worth_retrying(status: int) -> None:
    assert api_client.is_retryable(status)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
def test_statuses_not_worth_retrying(status: int) -> None:
    assert not api_client.is_retryable(status)


# --------------------------------------------------------------------------------------
# Heartbeat
# --------------------------------------------------------------------------------------


def test_heartbeat_body_matches_the_contract(settings: CollectorSettings) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"accepted": 1, "ignored": 0})

    account = api_client.HeartbeatAccount(
        account_id=ACCOUNT_ID, state="error", message="Неверный пароль инвестора", terminal_login=7
    )
    with _client(settings, handler) as api:
        api.heartbeat(COLLECTOR_ID, [account])

    assert seen["path"] == "/api/v1/ingest/heartbeat"
    assert seen["body"] == {
        "collector_id": COLLECTOR_ID,
        "accounts": [
            {
                "account_id": ACCOUNT_ID,
                "state": "error",
                "message": "Неверный пароль инвестора",
                "terminal_login": 7,
            }
        ],
    }


def test_heartbeat_omits_fields_the_server_treats_as_absent() -> None:
    """Модель границы закрыта `extra="forbid"`, но `message` и `terminal_login` необязательны."""
    body = api_client.HeartbeatAccount(account_id=ACCOUNT_ID, state="running").payload()
    assert body == {"account_id": ACCOUNT_ID, "state": "running"}


def test_long_message_is_trimmed_before_it_reaches_the_account_card() -> None:
    account = api_client.HeartbeatAccount(account_id=ACCOUNT_ID, state="error", message="я " * 400)
    assert len(account.payload()["message"]) <= 200
