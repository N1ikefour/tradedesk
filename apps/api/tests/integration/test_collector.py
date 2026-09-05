"""Канал управления коллектором против настоящих Postgres и Redis — DoD S1-05.

Три вещи здесь проверяются не формой ответа, а состоянием таблиц и содержимым логов,
потому что именно так они и ломаются молча:

* пароль ищется как **значение** — в теле ответа он обязан быть ровно один раз,
  в логах не должен встречаться никогда;
* закрепление коллектора за счётом читается из `trading_accounts.collector_id`;
* переходы статусов читаются из `trading_accounts.status`, а не из того, что вернул
  heartbeat.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from alembic import command
from app.core.config import get_settings
from app.core.db import get_engine, get_session_factory
from app.core.logging import REDACTED
from app.core.redis import get_redis
from app.domains.accounts import service as accounts
from app.domains.accounts.models import TradingAccount
from app.domains.collector import service as collector_service

pytestmark = pytest.mark.integration

API = "/api/v1"
API_DIR = Path(__file__).resolve().parents[2]

ORIGIN = "http://test"
CLIENT_IP = "203.0.113.11"
EMAIL = "collector-owner@example.test"

ACCOUNTS = f"{API}/accounts"
ASSIGNMENTS = f"{API}/internal/collector/assignments"
HEARTBEAT = f"{API}/ingest/heartbeat"

# То же значение, что ставит фикстура `local_env`.
COLLECTOR_TOKEN = "test-collector-token"
COLLECTOR = "desk-01"
OTHER_COLLECTOR = "desk-02"

# Значение, которого нет больше нигде: по нему обыскиваются тела ответов и логи.
INVESTOR_PASSWORD = "s3cret-investor-pw-4b7e0d"

MT5_BODY: dict[str, Any] = {
    "label": "Демо FTMO",
    "platform": "mt5",
    "is_demo": True,
    "server": "FTMO-Demo",
    "login": 7001234,
    "password": INVESTOR_PASSWORD,
}

_CODE_RE = re.compile(r"\b\d{6}\b")

_TABLES = (
    "users, otp_codes, sessions, dev_outbox, trading_accounts, account_credentials, "
    "deals, positions, sync_runs, journal_entries, reflections, attachments, tags"
)


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine", dbname="td_test") as container:
        yield container


@pytest.fixture(scope="module")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture(scope="module")
def schema(postgres: PostgresContainer) -> Iterator[None]:
    """Миграции — один раз на модуль; между тестами чистятся только данные.

    `get_settings.cache_clear()` вокруг обеих команд обязателен: `alembic/env.py` читает
    URL через `lru_cache`, а функциональная фикстура `reset_app_state` до setup и
    teardown модуля не дотягивается (разобрано в `test_accounts.py`).
    """
    url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("APP_ENV", "local")
        monkeypatch.setenv("DATABASE_URL", url)
        config = Config(str(API_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(API_DIR / "alembic"))
        get_settings.cache_clear()
        command.upgrade(config, "head")
        yield
        command.downgrade(config, "base")
    get_settings.cache_clear()


@pytest.fixture
def live_env(
    local_env: pytest.MonkeyPatch,
    schema: None,
    postgres: PostgresContainer,
    redis_container: RedisContainer,
) -> pytest.MonkeyPatch:
    url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    local_env.setenv("DATABASE_URL", url)
    local_env.setenv(
        "REDIS_URL",
        f"redis://{redis_container.get_container_host_ip()}:"
        f"{redis_container.get_exposed_port(6379)}/0",
    )
    return local_env


@pytest.fixture(autouse=True)
async def clean_state(live_env: pytest.MonkeyPatch) -> AsyncIterator[None]:
    async with get_engine().begin() as connection:
        await connection.execute(text(f"truncate {_TABLES} cascade"))
    await get_redis().flushdb()
    yield


@pytest.fixture
async def app(live_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]) -> FastAPI:
    return make_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Пользователь с сессией: им заводятся счета."""
    transport = ASGITransport(app=app, client=(CLIENT_IP, 51234))
    async with AsyncClient(
        transport=transport, base_url=ORIGIN, headers={"origin": ORIGIN}
    ) as opened:
        await login(opened, EMAIL)
        yield opened


@pytest.fixture
def log_stream(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Поток, в который приложение печатает логи.

    Перехват pytest тут не годится: `configure_logging` запоминает `sys.stdout` в
    обработчике на момент сборки приложения, а `capsys` подменяет поток позже — часть
    записей уходит мимо него, и проверка «пароля в логах нет» становится ложно зелёной.
    Подменяется сам поток обработчика: в тесте оказывается ровно то, что приложение
    отрендерило, вместе с работой JSON-рендерера и скраба.
    """
    stream = io.StringIO()
    monkeypatch.setattr(logging.getLogger().handlers[0], "stream", stream)
    return stream


@pytest.fixture
async def collector(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Коллектор: сервисный токен вместо cookie и без заголовка `Origin`.

    Заголовка нет намеренно — так ходит не-браузер, и `OriginCheckMiddleware` его
    пропускает (SPEC.md 4). Если проверка Origin однажды начнёт требовать заголовок,
    здесь это станет видно сразу.
    """
    transport = ASGITransport(app=app, client=(CLIENT_IP, 51235))
    async with AsyncClient(
        transport=transport,
        base_url=ORIGIN,
        headers={"authorization": f"Bearer {COLLECTOR_TOKEN}"},
    ) as opened:
        yield opened


async def read_code(client: AsyncClient) -> str:
    response = await client.get(f"{API}/dev/outbox")
    assert response.status_code == 200
    found = _CODE_RE.search(response.json()["items"][0]["body_text"])
    assert found is not None
    return found.group()


async def login(client: AsyncClient, email: str) -> None:
    assert (await client.post(f"{API}/auth/request-code", json={"email": email})).status_code == 202
    response = await client.post(
        f"{API}/auth/verify", json={"email": email, "code": await read_code(client)}
    )
    assert response.status_code == 200


async def execute(statement: str, **params: Any) -> None:
    async with get_engine().begin() as connection:
        await connection.execute(text(statement), params)


async def row_of(account_id: str) -> dict[str, Any]:
    async with get_engine().connect() as connection:
        row = (
            await connection.execute(
                text(
                    "select status, status_message, collector_id, last_heartbeat_at, "
                    "last_sync_at from trading_accounts where id = :id"
                ),
                {"id": account_id},
            )
        ).one()
    return dict(row._mapping)


async def create_account(client: AsyncClient, **overrides: Any) -> str:
    response = await client.post(ACCOUNTS, json={**MT5_BODY, **overrides})
    assert response.status_code == 201, response.text
    created = response.json()["id"]
    assert isinstance(created, str)
    return created


async def ask_assignments(
    collector: AsyncClient, collector_id: str = COLLECTOR
) -> list[dict[str, Any]]:
    response = await collector.get(ASSIGNMENTS, params={"collector_id": collector_id})
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict) and set(body) == {"items"}, body
    items = body["items"]
    assert isinstance(items, list)
    return items


async def send_heartbeat(
    collector: AsyncClient,
    accounts_payload: list[dict[str, Any]],
    collector_id: str = COLLECTOR,
) -> dict[str, int]:
    response = await collector.post(
        HEARTBEAT, json={"collector_id": collector_id, "accounts": accounts_payload}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


async def age_heartbeat(account_id: str, minutes: int) -> None:
    await execute(
        "update trading_accounts set last_heartbeat_at = now() - make_interval(mins => :m) "
        "where id = :id",
        id=account_id,
        m=minutes,
    )


async def run_sync_result(account_id: str, **kwargs: Any) -> None:
    """Успешный синк глазами домена счетов: то, что позовёт `POST /ingest/deals` (S1-04).

    Зовётся напрямую, потому что переход `pending → connected` принадлежит
    `apply_sync_result`, а маршрута ингеста ещё нет. Второго производителя этого
    перехода в системе нет — см. таблицу в `accounts.apply_heartbeat`.
    """
    async with get_session_factory()() as session:
        account = (
            await session.execute(
                select(TradingAccount).where(TradingAccount.id == UUID(account_id))
            )
        ).scalar_one()
        accounts.apply_sync_result(account, **kwargs)
        await session.commit()


async def run_check_collectors(now: datetime | None = None) -> list[UUID]:
    async with get_session_factory()() as session:
        return await accounts.check_collectors(session, now=now)


def log_lines(output: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            lines.append(parsed)
    return lines


# --- assignments -------------------------------------------------------------


async def test_assignment_carries_everything_the_collector_needs(
    client: AsyncClient, collector: AsyncClient
) -> None:
    """SPEC.md 5.6: состав ответа, включая `sync_requested_at` — без него `sync-now`
    остаётся меткой, которую никто не читает."""
    account_id = await create_account(client)
    assert (await client.post(f"{ACCOUNTS}/{account_id}/sync-now")).status_code == 202

    items = await ask_assignments(collector)

    assert len(items) == 1
    issued = items[0]
    assert set(issued) == {
        "account_id",
        "server",
        "login",
        "password",
        "sync_requested_at",
        "last_sync_at",
        "status",
    }
    assert issued["account_id"] == account_id
    assert issued["server"] == MT5_BODY["server"]
    assert issued["login"] == MT5_BODY["login"]
    assert issued["password"] == INVESTOR_PASSWORD
    assert issued["status"] == accounts.STATUS_PENDING
    assert issued["last_sync_at"] is None
    assert issued["sync_requested_at"] is not None
    assert issued["sync_requested_at"].endswith("Z")


async def test_assignment_claims_the_account(client: AsyncClient, collector: AsyncClient) -> None:
    """`GET`, который пишет: SPEC.md 5.6 требует зафиксировать коллектор за счётом."""
    account_id = await create_account(client)
    assert (await row_of(account_id))["collector_id"] is None

    await ask_assignments(collector)

    assert (await row_of(account_id))["collector_id"] == COLLECTOR


async def test_claimed_account_is_not_given_to_another_collector(
    client: AsyncClient, collector: AsyncClient
) -> None:
    """Два терминала в одном брокерском аккаунте — то, ради чего закрепление и есть."""
    account_id = await create_account(client)
    await ask_assignments(collector, COLLECTOR)

    assert await ask_assignments(collector, OTHER_COLLECTOR) == []
    assert (await row_of(account_id))["collector_id"] == COLLECTOR


async def test_two_collectors_asking_at_once_never_get_the_same_account(
    client: AsyncClient,
) -> None:
    """Та же гарантия, что выше, но в одновременности — иначе она ничем не закреплена.

    Последовательные запросы прошли бы и на реализации «прочитал, потом записал»: ко
    второму запросу первый уже записан, и гонки просто нет. Здесь два `issue_assignments`
    на **разных сессиях** уходят в базу одновременно, и проверяется пустое пересечение
    выдач. Две мутации, снимающие гарантию, — убрать `WHERE collector_id IS NULL` и
    заменить один UPDATE на select+update — красят этот тест и никакой другой.
    """
    created = {await create_account(client, label=f"Счёт {n}", login=7004000 + n) for n in range(3)}

    factory = get_session_factory()
    async with factory() as first, factory() as second:
        # Соединение берётся до гонки намеренно. Без прогрева гонки не будет вовсе:
        # вторая сессия сначала здоровается с Postgres, а первая за это время успевает
        # закрепить счета и закоммитить — измерено, «одновременность» оказывалась
        # последовательностью, и тест был бы ложно зелёным.
        await asyncio.gather(first.execute(text("select 1")), second.execute(text("select 1")))
        batches = await asyncio.gather(
            collector_service.issue_assignments(first, COLLECTOR),
            collector_service.issue_assignments(second, OTHER_COLLECTOR),
        )
    left, right = ({str(item.account.id) for item in batch} for batch in batches)

    assert left & right == set()
    assert left | right == created
    for account_id in left:
        assert (await row_of(account_id))["collector_id"] == COLLECTOR
    for account_id in right:
        assert (await row_of(account_id))["collector_id"] == OTHER_COLLECTOR


async def test_repeated_request_by_the_same_collector_changes_nothing(
    client: AsyncClient, collector: AsyncClient
) -> None:
    account_id = await create_account(client)

    first = await ask_assignments(collector)
    second = await ask_assignments(collector)

    assert first == second
    assert (await row_of(account_id))["collector_id"] == COLLECTOR


@pytest.mark.parametrize("route", ["pause", "archive"])
async def test_account_out_of_work_is_not_issued(
    client: AsyncClient, collector: AsyncClient, route: str
) -> None:
    """`paused` и `archived` — решения пользователя; коллектору их знать незачем."""
    account_id = await create_account(client)
    assert (await client.post(f"{ACCOUNTS}/{account_id}/{route}")).status_code == 200

    assert await ask_assignments(collector) == []


async def test_non_mt5_account_is_not_issued(client: AsyncClient, collector: AsyncClient) -> None:
    """У ручного счёта нет ни сервера, ни логина: войти коллектору некуда.

    Проверяется не только пустая выдача. Счёт, попавший в выборку и отсеянный уже на
    расшифровке, выглядел бы так же — но при этом закрепился бы за коллектором и уехал
    в `needs_attention` с просьбой ввести пароль, которого у него нет и не должно быть.
    """
    response = await client.post(
        ACCOUNTS, json={"label": "Ручной", "platform": "manual", "is_demo": False}
    )
    assert response.status_code == 201, response.text
    account_id = response.json()["id"]

    assert await ask_assignments(collector) == []
    row = await row_of(account_id)
    assert row["collector_id"] is None
    assert row["status"] == accounts.STATUS_PENDING
    assert row["status_message"] is None


async def test_assignments_are_ordered_deterministically(
    client: AsyncClient, collector: AsyncClient
) -> None:
    first = await create_account(client, label="Первый", login=7001001)
    second = await create_account(client, label="Второй", login=7001002)

    issued = [item["account_id"] for item in await ask_assignments(collector)]

    assert issued == [first, second]


async def test_unreadable_credentials_are_skipped_and_reported(
    client: AsyncClient, collector: AsyncClient
) -> None:
    """Один нечитаемый счёт не должен уносить с собой всю выдачу установки.

    И молчать о нём нельзя: `needs_attention` — единственный способ, которым
    пользователь узнает, что пароль надо ввести заново.
    """
    broken = await create_account(client, label="Битый", login=7002001)
    healthy = await create_account(client, label="Живой", login=7002002)
    await execute(
        "update account_credentials set ciphertext = decode('0102030405', 'hex') "
        "where account_id = :id",
        id=broken,
    )

    issued = [item["account_id"] for item in await ask_assignments(collector)]

    assert issued == [healthy]
    assert (await row_of(broken))["status"] == accounts.STATUS_NEEDS_ATTENTION
    assert (await row_of(broken))["status_message"] == (
        collector_service.CREDENTIALS_UNREADABLE_MESSAGE
    )


async def test_password_reaches_the_collector_but_never_the_log(
    client: AsyncClient, collector: AsyncClient, log_stream: io.StringIO
) -> None:
    """SPEC.md 5.6: доступ логируется (`account_id`, `collector_id`, время) без пароля.

    Обе половины проверяются вместе. Без первой тест остался бы зелёным, если бы
    журнала доступа не было вовсе, — и перестал бы что-либо доказывать.

    Счетов два намеренно: на одном «запись на счёт» и «запись на запрос» неотличимы, а
    `issue_assignments` обещает первое — журнал того, что пароль покинул систему, а не
    счётчик обращений.
    """
    first = await create_account(client, label="Первый", login=7005001)
    second = await create_account(client, label="Второй", login=7005002)

    items = await ask_assignments(collector)
    output = log_stream.getvalue()

    assert [item["password"] for item in items] == [INVESTOR_PASSWORD, INVESTOR_PASSWORD]
    audit = [line for line in log_lines(output) if line["event"] == "collector.credentials_issued"]
    assert [line["account_id"] for line in audit] == [first, second]
    assert {line["collector_id"] for line in audit} == {COLLECTOR}
    assert all(line["timestamp"] for line in audit)
    assert INVESTOR_PASSWORD not in output


# --- heartbeat ---------------------------------------------------------------


async def test_error_state_moves_the_account_to_needs_attention(
    client: AsyncClient, collector: AsyncClient
) -> None:
    account_id = await create_account(client)
    await ask_assignments(collector)

    result = await send_heartbeat(
        collector,
        [{"account_id": account_id, "state": "error", "message": "Неверный пароль инвестора"}],
    )

    assert result == {"accepted": 1, "ignored": 0}
    row = await row_of(account_id)
    assert row["status"] == accounts.STATUS_NEEDS_ATTENTION
    assert row["status_message"] == "Неверный пароль инвестора"
    assert row["last_heartbeat_at"] is not None


async def test_error_without_a_message_still_says_something(
    client: AsyncClient, collector: AsyncClient
) -> None:
    """Красный статус без причины — худшее, что можно показать в карточке счёта."""
    account_id = await create_account(client)

    await send_heartbeat(collector, [{"account_id": account_id, "state": "error"}])

    assert (await row_of(account_id))["status_message"] == accounts.COLLECTOR_ERROR_MESSAGE


@pytest.mark.parametrize("state", ["running", "stopped"])
async def test_alive_states_refresh_the_heartbeat_without_touching_status(
    client: AsyncClient, collector: AsyncClient, state: str
) -> None:
    """`stopped` — штатное выключение, а не поломка; молчание подберёт `check_collectors`."""
    account_id = await create_account(client)

    result = await send_heartbeat(collector, [{"account_id": account_id, "state": state}])

    assert result == {"accepted": 1, "ignored": 0}
    row = await row_of(account_id)
    assert row["status"] == accounts.STATUS_PENDING
    assert row["status_message"] is None
    assert row["last_heartbeat_at"] is not None


async def test_heartbeat_never_returns_the_account_to_connected(
    client: AsyncClient, collector: AsyncClient
) -> None:
    """У перехода в `connected` один производитель — успешный синк.

    Живой процесс коллектора доказывает, что процесс жив, а не что счёт синкается,
    и о чужих причинах `needs_attention` (например, о валюте) он ничего не знает.
    """
    account_id = await create_account(client)
    await send_heartbeat(
        collector, [{"account_id": account_id, "state": "error", "message": "Терминал не запущен"}]
    )

    await send_heartbeat(collector, [{"account_id": account_id, "state": "running"}])

    row = await row_of(account_id)
    assert row["status"] == accounts.STATUS_NEEDS_ATTENTION
    assert row["status_message"] == "Терминал не запущен"


@pytest.mark.parametrize("route", ["pause", "archive"])
async def test_heartbeat_does_not_touch_accounts_out_of_work(
    client: AsyncClient, collector: AsyncClient, route: str
) -> None:
    """`paused` и `archived` heartbeat не меняет — включая `last_heartbeat_at`."""
    account_id = await create_account(client)
    assert (await client.post(f"{ACCOUNTS}/{account_id}/{route}")).status_code == 200
    before = await row_of(account_id)

    result = await send_heartbeat(
        collector, [{"account_id": account_id, "state": "error", "message": "не запускается"}]
    )

    assert result == {"accepted": 0, "ignored": 1}
    assert await row_of(account_id) == before


async def test_foreign_collector_cannot_touch_the_account(
    client: AsyncClient, collector: AsyncClient
) -> None:
    """Счёт, который коллектору не выдавали, он не вправе и переключить."""
    account_id = await create_account(client)
    await ask_assignments(collector, COLLECTOR)
    before = await row_of(account_id)

    result = await send_heartbeat(
        collector,
        [{"account_id": account_id, "state": "error", "message": "чужая ошибка"}],
        collector_id=OTHER_COLLECTOR,
    )

    assert result == {"accepted": 0, "ignored": 1}
    assert await row_of(account_id) == before


async def test_unknown_account_is_ignored_not_an_error(
    client: AsyncClient, collector: AsyncClient
) -> None:
    """Один посторонний идентификатор не должен ронять heartbeat остальных счетов."""
    account_id = await create_account(client)

    result = await send_heartbeat(
        collector,
        [
            {"account_id": account_id, "state": "running"},
            {"account_id": "00000000-0000-4000-8000-000000000000", "state": "running"},
        ],
    )

    assert result == {"accepted": 1, "ignored": 1}


async def test_empty_heartbeat_is_accepted(collector: AsyncClient) -> None:
    assert await send_heartbeat(collector, []) == {"accepted": 0, "ignored": 0}


async def test_collector_message_is_scrubbed_before_it_reaches_every_screen(
    client: AsyncClient, collector: AsyncClient
) -> None:
    """X-21, второй канал: `status_message` отдаётся каждым маршрутом счетов.

    Проверяется тот самый маршрут, который читают все экраны, — `GET /accounts`.
    """
    account_id = await create_account(client)
    await send_heartbeat(
        collector,
        [
            {
                "account_id": account_id,
                "state": "error",
                "message": f"вход отклонён\nservice token={COLLECTOR_TOKEN}\r\n" + "хвост " * 100,
            }
        ],
    )

    response = await client.get(ACCOUNTS)
    card = response.json()["items"][0]

    assert COLLECTOR_TOKEN not in response.text
    assert REDACTED in card["status_message"]
    assert "\n" not in card["status_message"] and "\r" not in card["status_message"]
    assert len(card["status_message"]) <= 200
    # Диагностируемость не потеряна: то, что не секрет, осталось на месте.
    assert card["status_message"].startswith("вход отклонён")


# --- переходы статусов и check_collectors ------------------------------------


async def test_pending_connected_needs_attention(
    client: AsyncClient, collector: AsyncClient
) -> None:
    """Цепочка из DoD S1-05 целиком, каждым её настоящим производителем."""
    account_id = await create_account(client)
    await ask_assignments(collector)
    await send_heartbeat(collector, [{"account_id": account_id, "state": "running"}])
    assert (await row_of(account_id))["status"] == accounts.STATUS_PENDING

    await run_sync_result(account_id, currency="USD", margin_mode="hedging")
    assert (await row_of(account_id))["status"] == accounts.STATUS_CONNECTED

    await age_heartbeat(account_id, minutes=6)
    affected = await run_check_collectors()

    assert affected == [UUID(account_id)]
    row = await row_of(account_id)
    assert row["status"] == accounts.STATUS_NEEDS_ATTENTION
    assert row["status_message"] == accounts.COLLECTOR_OFFLINE_MESSAGE


async def test_heartbeat_alone_does_not_make_the_account_connected(
    client: AsyncClient, collector: AsyncClient
) -> None:
    """Обратная сторона предыдущего: без синка `connected` не появляется."""
    account_id = await create_account(client)

    await send_heartbeat(collector, [{"account_id": account_id, "state": "running"}])

    assert (await row_of(account_id))["status"] == accounts.STATUS_PENDING


async def test_fresh_heartbeat_survives_the_check(
    client: AsyncClient, collector: AsyncClient
) -> None:
    account_id = await create_account(client)
    await run_sync_result(account_id, currency="USD")
    await age_heartbeat(account_id, minutes=4)

    assert await run_check_collectors() == []
    assert (await row_of(account_id))["status"] == accounts.STATUS_CONNECTED


async def test_account_without_a_heartbeat_is_not_declared_offline(
    client: AsyncClient,
) -> None:
    """Счёт, которому коллектор не отвечал никогда, — это CSV или советник (SPEC.md 5.3).

    Сказать про него «коллектор не на связи» было бы неправдой, а `connected` он
    получил законно — успешным синком.
    """
    account_id = await create_account(client)
    await run_sync_result(account_id, currency="USD")
    assert (await row_of(account_id))["last_heartbeat_at"] is None

    assert await run_check_collectors() == []
    assert (await row_of(account_id))["status"] == accounts.STATUS_CONNECTED


@pytest.mark.parametrize("route", ["pause", "archive"])
async def test_check_collectors_leaves_accounts_out_of_work_alone(
    client: AsyncClient, route: str
) -> None:
    account_id = await create_account(client)
    await run_sync_result(account_id, currency="USD")
    await age_heartbeat(account_id, minutes=30)
    assert (await client.post(f"{ACCOUNTS}/{account_id}/{route}")).status_code == 200
    before = await row_of(account_id)

    assert await run_check_collectors() == []
    assert await row_of(account_id) == before


async def test_check_collectors_leaves_pending_alone(client: AsyncClient) -> None:
    """SPEC.md 10 говорит про счета «со статусом `connected`». `pending` ждёт первый синк,
    и «коллектор не на связи» ему не добавляет ничего нового."""
    account_id = await create_account(client)
    await age_heartbeat(account_id, minutes=30)

    assert await run_check_collectors() == []
    assert (await row_of(account_id))["status"] == accounts.STATUS_PENDING


async def test_check_collectors_uses_the_five_minute_threshold(client: AsyncClient) -> None:
    """Порог — тот же, что у `is_collector_online` и у экрана счетов (SPEC.md 9.3, 10)."""
    account_id = await create_account(client)
    await run_sync_result(account_id, currency="USD")
    await age_heartbeat(account_id, minutes=5)
    now = datetime.now(UTC)

    # На самой границе счёт ещё на связи, секундой позже — уже нет.
    assert await run_check_collectors(now=now - timedelta(seconds=1)) == []
    assert await run_check_collectors(now=now + timedelta(seconds=1)) == [UUID(account_id)]


async def test_check_collectors_is_idempotent(client: AsyncClient) -> None:
    """Cron раз в минуту: второй прогон не должен ни падать, ни переписывать заново."""
    account_id = await create_account(client)
    await run_sync_result(account_id, currency="USD")
    await age_heartbeat(account_id, minutes=6)

    assert await run_check_collectors() == [UUID(account_id)]
    assert await run_check_collectors() == []
