"""Счета против настоящих Postgres и Redis — DoD S1-06.

Вход выполняется настоящим потоком OTP, а не подставленной строкой в `sessions`: всё
здесь висит на владельце, и проверять границу владельца на выдуманной сессии нечестно.

Три вещи проверяются запросом к таблицам, а не формой ответа, потому что именно так они
и ломаются молча:

* пароль ищется как **значение** в теле каждого ответа домена;
* архив — по отсутствию строки в `account_credentials`;
* удаление — по отсутствию строк в `deals`, `positions` и пользовательском слое.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from alembic import command
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.redis import get_redis
from app.domains.accounts.schemas import ACCOUNT_COLORS

pytestmark = pytest.mark.integration

API = "/api/v1"
API_DIR = Path(__file__).resolve().parents[2]

ORIGIN = "http://test"
CLIENT_IP = "203.0.113.10"
EMAIL = "trader@example.test"
OTHER_EMAIL = "other@example.test"

ACCOUNTS = f"{API}/accounts"

# SPEC.md 5.2: «последние 50 sync_runs». Число продублировано, а не импортировано из
# роутера намеренно: тест сверяет ответ со спекой, а взятое из роутера значение
# подстроилось бы под любую его правку и предел перестал бы быть проверяемым.
SPEC_SYNC_RUNS_LIMIT = 50

# Значение, которого нет больше нигде: по нему тело ответа обыскивается на утечку.
INVESTOR_PASSWORD = "s3cret-investor-pw-9f2a1c"

# Тело формы после `T-07`: пароля в нём нет, и это единственный путь в интерфейсе. Там,
# где проверяется сам пароль, он передаётся явным `password=INVESTOR_PASSWORD` — так же,
# как это делает клиент, написанный до этого решения.
MT5_BODY: dict[str, Any] = {
    "label": "Демо FTMO",
    "platform": "mt5",
    "is_demo": True,
    "server": "FTMO-Demo",
    "login": 5001234,
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

    `get_settings.cache_clear()` вокруг обеих команд обязателен, хотя в соседних модулях
    его нет. `alembic/env.py` берёт URL из `get_settings()`, а это `lru_cache` на процесс;
    сбрасывает его функциональная фикстура `reset_app_state`, то есть между тестами, — а
    эти вызовы идут в setup и teardown **модуля**, вне её охвата. Без сброса `downgrade`
    здесь кэширует URL нашего контейнера, контейнер следом останавливается, и `upgrade`
    следующего модуля пытается подключиться к мёртвому порту. Раньше это не всплывало
    только потому, что модуль с такой фикстурой шёл в наборе первым.
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


def make_client(app: FastAPI) -> AsyncClient:
    """Origin проставлен по умолчанию: так ходит браузер и так проходит проверка CSRF."""
    transport = ASGITransport(app=app, client=(CLIENT_IP, 51234))
    return AsyncClient(transport=transport, base_url=ORIGIN, headers={"origin": ORIGIN})


@pytest.fixture
async def app(live_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]) -> FastAPI:
    return make_app()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with make_client(app) as opened:
        await login(opened, EMAIL)
        yield opened


@pytest.fixture
async def other_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Второй пользователь того же приложения: своя cookie, своя строка в `users`."""
    async with make_client(app) as opened:
        await login(opened, OTHER_EMAIL)
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


async def scalar(statement: str, **params: Any) -> Any:
    async with get_engine().connect() as connection:
        return (await connection.execute(text(statement), params)).scalar()


async def execute(statement: str, **params: Any) -> None:
    async with get_engine().begin() as connection:
        await connection.execute(text(statement), params)


async def credentials_rows(account_id: str) -> int:
    return await scalar(
        "select count(*) from account_credentials where account_id = :id", id=account_id
    )


async def create_account(client: AsyncClient, **overrides: Any) -> dict[str, Any]:
    response = await client.post(ACCOUNTS, json={**MT5_BODY, **overrides})
    assert response.status_code == 201, response.text
    body = response.json()
    assert isinstance(body, dict)
    return body


async def status_of(account_id: str) -> tuple[Any, Any]:
    async with get_engine().connect() as connection:
        row = (
            await connection.execute(
                text("select status, status_message from trading_accounts where id = :id"),
                {"id": account_id},
            )
        ).one()
    return row[0], row[1]


def error_code(response: Response) -> str:
    code = response.json()["error"]["code"]
    assert isinstance(code, str)
    return code


async def seed_history(account_id: str) -> UUID:
    """Одна позиция с двумя сделками, прогоном синка и полным пользовательским слоем."""
    position_id = uuid4()
    await execute(
        """
        insert into positions (
            id, account_id, position_id, symbol_raw, symbol_norm, direction, status,
            open_time, close_time, volume_opened, volume_closed, avg_entry_price,
            avg_exit_price, deals_count, rebuilt_at
        ) values (
            :id, :account, 777, 'EURUSD.m', 'EURUSD', 'long', 'closed',
            now(), now(), 0.1, 0.1, 1.08543, 1.08643, 2, now()
        )
        """,
        id=position_id,
        account=account_id,
    )
    for ticket, entry in ((1, "in"), (2, "out")):
        await execute(
            """
            insert into deals (
                account_id, deal_ticket, position_id, symbol_raw, deal_type, entry,
                volume, price, profit, time_utc, time_server, raw, source
            ) values (
                :account, :ticket, 777, 'EURUSD.m', 'buy', :entry,
                0.1, 1.08543, 10.00, now(), now(), '{}'::jsonb, 'collector'
            )
            """,
            account=account_id,
            ticket=ticket,
            entry=entry,
        )
    await execute(
        """
        insert into sync_runs (account_id, source, started_at, finished_at, deals_received)
        values (:account, 'collector', now(), now(), 2)
        """,
        account=account_id,
    )
    await execute(
        "insert into journal_entries (position_id, notes, updated_at) "
        "values (:id, 'заметка', now())",
        id=position_id,
    )
    await execute(
        "insert into reflections (position_id, confidence, updated_at) values (:id, 4, now())",
        id=position_id,
    )
    await execute(
        """
        insert into attachments (id, position_id, s3_key, content_type, created_at)
        values (gen_random_uuid(), :id, 'k', 'image/png', now())
        """,
        id=position_id,
    )
    return position_id


# --- пароль не выходит наружу ------------------------------------------------


async def test_password_never_appears_in_any_accounts_response(client: AsyncClient) -> None:
    """Ключевой инвариант S1-06: `CLAUDE.md` §5 — пароль не покидает сервер.

    Проверяется **значение**, а не имя поля: утечка под безобидным именем (`hint`,
    `investor`, `note`) прошла бы мимо любой проверки схемы. Обходятся все успешные
    ответы домена, включая заголовки.

    Счёт заводится с паролем намеренно, хотя форма его больше не спрашивает (`T-07`):
    без сохранённого пароля искать в ответах было бы нечего, и тест перестал бы
    что-либо доказывать.
    """
    created = await create_account(client, password=INVESTOR_PASSWORD)
    account_id = created["id"]

    responses = [
        await client.post(
            ACCOUNTS,
            json={
                **MT5_BODY,
                "label": "Второй",
                "login": 5001235,
                "password": INVESTOR_PASSWORD,
            },
        ),
        await client.get(ACCOUNTS),
        await client.get(f"{ACCOUNTS}?include_archived=true"),
        await client.patch(f"{ACCOUNTS}/{account_id}", json={"password": INVESTOR_PASSWORD}),
        await client.patch(f"{ACCOUNTS}/{account_id}", json={"label": "Переименован"}),
        await client.post(f"{ACCOUNTS}/{account_id}/pause"),
        await client.post(f"{ACCOUNTS}/{account_id}/resume"),
        await client.post(f"{ACCOUNTS}/{account_id}/sync-now"),
        await client.get(f"{ACCOUNTS}/{account_id}/sync-runs"),
        await client.post(f"{ACCOUNTS}/{account_id}/archive"),
    ]

    leaked = [
        (response.request.method, str(response.request.url))
        for response in responses
        if INVESTOR_PASSWORD in response.text or INVESTOR_PASSWORD in str(response.headers)
    ]
    assert leaked == [], f"пароль в ответе: {leaked}"
    # Обход был не по пустым ответам: каждый маршрут действительно отработал.
    assert [response.status_code for response in responses] == [
        201,
        *[200] * 6,
        202,  # sync-now: расписка о принятой просьбе, а не результат синка
        *[200] * 2,
    ]


async def test_password_is_stored_encrypted_and_not_in_plain_text(client: AsyncClient) -> None:
    """Второй конец того же инварианта: в БД лежит шифротекст, а не пароль.

    Механизм шифрования `T-07` не трогает (ADR-0003, ADR-0006): у первого пользователя
    сохранённые пароли уже есть, и они обязаны пережить обновление ровно такими.
    """
    created = await create_account(client, password=INVESTOR_PASSWORD)

    ciphertext = await scalar(
        "select ciphertext from account_credentials where account_id = :id", id=created["id"]
    )

    assert ciphertext is not None
    assert INVESTOR_PASSWORD.encode() not in ciphertext
    # Длина шифротекста не выдаёт длину пароля: открытый текст добит до кратного блока.
    assert len(ciphertext) > len(INVESTOR_PASSWORD) + 32


# --- создание ----------------------------------------------------------------


async def test_create_returns_pending_account_with_defaults(client: AsyncClient) -> None:
    created = await create_account(client)

    assert created["status"] == "pending"
    assert created["currency"] == "USD"
    assert created["positions_count"] == 0
    assert created["color"] == ACCOUNT_COLORS[0]
    assert created["last_sync_at"] is None
    assert created["created_at"].endswith("Z")
    # `T-07`: пароля в теле нет, и строки credentials у нового счёта не появляется.
    assert await credentials_rows(created["id"]) == 0


async def test_colors_are_handed_out_from_the_palette(client: AsyncClient) -> None:
    first = await create_account(client)
    second = await create_account(client, label="Второй", login=5001235)

    assert first["color"] != second["color"]
    assert {first["color"], second["color"]} <= set(ACCOUNT_COLORS)


async def test_manual_account_has_no_credentials(client: AsyncClient) -> None:
    response = await client.post(ACCOUNTS, json={"label": "Ручной", "platform": "manual"})

    assert response.status_code == 201
    assert await credentials_rows(response.json()["id"]) == 0


async def test_duplicate_mt5_identity_is_409(client: AsyncClient) -> None:
    await create_account(client)

    response = await client.post(ACCOUNTS, json={**MT5_BODY, "label": "Он же"})

    assert response.status_code == 409
    assert error_code(response) == "account_already_exists"


async def test_same_identity_belongs_to_each_user_separately(
    client: AsyncClient, other_client: AsyncClient
) -> None:
    """Уникальность — в пределах пользователя: один демо-сервер бывает у двоих."""
    await create_account(client)

    assert (await other_client.post(ACCOUNTS, json=MT5_BODY)).status_code == 201


# --- список ------------------------------------------------------------------


async def test_list_counts_positions_and_hides_archived(client: AsyncClient) -> None:
    created = await create_account(client)
    await seed_history(created["id"])
    other = await create_account(client, label="Второй", login=5001235)

    listed = (await client.get(ACCOUNTS)).json()["items"]
    assert [item["positions_count"] for item in listed] == [1, 0]

    await client.post(f"{ACCOUNTS}/{other['id']}/archive")

    assert [item["id"] for item in (await client.get(ACCOUNTS)).json()["items"]] == [created["id"]]
    with_archived = (await client.get(f"{ACCOUNTS}?include_archived=true")).json()["items"]
    assert {item["id"] for item in with_archived} == {created["id"], other["id"]}


async def test_list_shows_only_own_accounts(client: AsyncClient, other_client: AsyncClient) -> None:
    mine = await create_account(client)
    await other_client.post(ACCOUNTS, json={**MT5_BODY, "label": "Чужой"})

    listed = (await client.get(ACCOUNTS)).json()["items"]

    assert [item["id"] for item in listed] == [mine["id"]]


async def test_list_is_ordered_by_sort_order(client: AsyncClient) -> None:
    first = await create_account(client)
    second = await create_account(client, label="Второй", login=5001235)
    await client.patch(f"{ACCOUNTS}/{first['id']}", json={"sort_order": 5})

    listed = (await client.get(ACCOUNTS)).json()["items"]

    assert [item["id"] for item in listed] == [second["id"], first["id"]]


# --- граница владельца -------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("patch", "", {"label": "Чужой"}),
        ("post", "/pause", None),
        ("post", "/resume", None),
        ("post", "/archive", None),
        ("post", "/sync-now", None),
        ("delete", "", None),
        ("get", "/sync-runs", None),
    ],
)
async def test_foreign_account_is_404_not_403(
    client: AsyncClient, other_client: AsyncClient, method: str, suffix: str, body: Any
) -> None:
    """403 подтвердил бы, что счёт существует. Ответ обязан быть неотличим от «нет такого»."""
    foreign = (await other_client.post(ACCOUNTS, json=MT5_BODY)).json()

    response = await client.request(method, f"{ACCOUNTS}/{foreign['id']}{suffix}", json=body)

    assert response.status_code == 404
    assert error_code(response) == "account_not_found"
    # Чужой счёт не тронут.
    assert (await status_of(foreign["id"]))[0] == "pending"


async def test_unknown_account_is_404(client: AsyncClient) -> None:
    response = await client.patch(f"{ACCOUNTS}/{uuid4()}", json={"label": "X"})

    assert response.status_code == 404
    assert error_code(response) == "account_not_found"


async def test_missing_and_foreign_are_indistinguishable(
    client: AsyncClient, other_client: AsyncClient
) -> None:
    foreign = (await other_client.post(ACCOUNTS, json=MT5_BODY)).json()

    absent = await client.post(f"{ACCOUNTS}/{uuid4()}/pause")
    someone_elses = await client.post(f"{ACCOUNTS}/{foreign['id']}/pause")

    assert absent.status_code == someone_elses.status_code
    assert absent.json() == someone_elses.json()


# --- правка ------------------------------------------------------------------


async def test_label_only_patch_keeps_the_connection(client: AsyncClient) -> None:
    """Развилка 4: переименование не должно останавливать работающий синк."""
    created = await create_account(client)
    await execute(
        "update trading_accounts set status = 'connected', last_sync_at = now() where id = :id",
        id=created["id"],
    )

    response = await client.patch(f"{ACCOUNTS}/{created['id']}", json={"label": "Новое имя"})

    assert response.status_code == 200
    assert response.json()["label"] == "Новое имя"
    assert response.json()["status"] == "connected"


async def test_resending_the_same_server_and_login_keeps_the_connection(
    client: AsyncClient,
) -> None:
    """Форма редактирования шлёт карточку целиком — значения те же, статус не трогаем."""
    created = await create_account(client)
    await execute(
        "update trading_accounts set status = 'connected' where id = :id", id=created["id"]
    )

    response = await client.patch(
        f"{ACCOUNTS}/{created['id']}",
        json={"label": "Новое", "server": MT5_BODY["server"], "login": MT5_BODY["login"]},
    )

    assert response.json()["status"] == "connected"


async def test_new_password_recreates_credentials_without_resetting_status(
    client: AsyncClient,
) -> None:
    """`T-07`: пароль перезаписывается, но состояние счёта не трогает.

    Раньше присланный пароль возвращал счёт в `pending` — коллектор входил в терминал
    заново. Входа нет, обещать его нечем, и синкающийся счёт не должен уходить в
    «ожидает коллектор» от правки, которая ни на что не влияет.
    """
    created = await create_account(client, password=INVESTOR_PASSWORD)
    await execute(
        "update trading_accounts set status = 'connected' where id = :id", id=created["id"]
    )
    before = await scalar(
        "select ciphertext from account_credentials where account_id = :id", id=created["id"]
    )

    response = await client.patch(f"{ACCOUNTS}/{created['id']}", json={"password": "другой-пароль"})

    assert response.status_code == 200
    assert response.json()["status"] == "connected"
    after = await scalar(
        "select ciphertext from account_credentials where account_id = :id", id=created["id"]
    )
    assert after != before
    assert await credentials_rows(created["id"]) == 1


async def test_changed_server_resets_status(client: AsyncClient) -> None:
    created = await create_account(client)
    await execute(
        "update trading_accounts set status = 'connected' where id = :id", id=created["id"]
    )

    response = await client.patch(f"{ACCOUNTS}/{created['id']}", json={"server": "FTMO-Real"})

    assert response.json()["status"] == "pending"
    assert response.json()["server"] == "FTMO-Real"


async def test_password_change_does_not_resume_a_paused_account(client: AsyncClient) -> None:
    """Возобновление синка — отдельное решение, а не побочный эффект правки формы."""
    created = await create_account(client)
    await client.post(f"{ACCOUNTS}/{created['id']}/pause")

    response = await client.patch(f"{ACCOUNTS}/{created['id']}", json={"password": "новый"})

    assert response.json()["status"] == "paused"


async def test_empty_patch_changes_nothing(client: AsyncClient) -> None:
    created = await create_account(client)
    await execute(
        "update trading_accounts set status = 'connected' where id = :id", id=created["id"]
    )

    response = await client.patch(f"{ACCOUNTS}/{created['id']}", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "connected"
    assert response.json()["label"] == MT5_BODY["label"]


async def test_patch_of_a_manual_account_rejects_mt5_fields(client: AsyncClient) -> None:
    manual = (await client.post(ACCOUNTS, json={"label": "Ручной", "platform": "manual"})).json()

    response = await client.patch(f"{ACCOUNTS}/{manual['id']}", json={"password": "х"})

    assert response.status_code == 422
    assert error_code(response) == "not_mt5_account"
    assert await credentials_rows(manual["id"]) == 0


async def test_patch_into_an_existing_identity_is_409(client: AsyncClient) -> None:
    await create_account(client)
    second = await create_account(client, label="Второй", login=5001235)

    response = await client.patch(f"{ACCOUNTS}/{second['id']}", json={"login": MT5_BODY["login"]})

    assert response.status_code == 409
    assert error_code(response) == "account_already_exists"
    # Откат транзакции: логин второго счёта остался прежним.
    listed = (await client.get(ACCOUNTS)).json()["items"]
    assert sorted(item["login"] for item in listed) == [5001234, 5001235]


async def test_broker_can_be_set_and_cleared(client: AsyncClient) -> None:
    created = await create_account(client)

    assert (await client.patch(f"{ACCOUNTS}/{created['id']}", json={"broker": "FTMO"})).json()[
        "broker"
    ] == "FTMO"
    assert (await client.patch(f"{ACCOUNTS}/{created['id']}", json={"broker": None})).json()[
        "broker"
    ] is None


# --- пауза и возобновление ---------------------------------------------------


async def test_pause_and_resume(client: AsyncClient) -> None:
    created = await create_account(client)
    await execute(
        "update trading_accounts set status = 'connected' where id = :id", id=created["id"]
    )

    assert (await client.post(f"{ACCOUNTS}/{created['id']}/pause")).json()["status"] == "paused"
    # Идемпотентно: повторная пауза — тот же ответ.
    assert (await client.post(f"{ACCOUNTS}/{created['id']}/pause")).json()["status"] == "paused"
    resumed = await client.post(f"{ACCOUNTS}/{created['id']}/resume")
    # Не `connected`: «синк был только что» подтверждает синк, а не наша память о нём.
    assert resumed.json()["status"] == "pending"


async def test_resume_of_a_working_account_changes_nothing(client: AsyncClient) -> None:
    created = await create_account(client)
    await execute(
        "update trading_accounts set status = 'connected' where id = :id", id=created["id"]
    )

    assert (await client.post(f"{ACCOUNTS}/{created['id']}/resume")).json()["status"] == "connected"


# --- архив -------------------------------------------------------------------


async def test_archive_deletes_credentials_from_the_table(client: AsyncClient) -> None:
    """DoD S1-06. Проверяется строка в БД, а не отсутствие поля в ответе.

    Ответ пароля не содержит никогда — по нему нельзя отличить «стёрли» от «не показываем».

    Счёт заводится с паролем: у счёта без него стирать нечего, и проверка прошла бы,
    ничего не проверив.
    """
    created = await create_account(client, password=INVESTOR_PASSWORD)
    assert await credentials_rows(created["id"]) == 1

    response = await client.post(f"{ACCOUNTS}/{created['id']}/archive")

    assert response.status_code == 200
    assert response.json()["status"] == "archived"
    assert await credentials_rows(created["id"]) == 0


async def test_archive_keeps_the_deals(client: AsyncClient) -> None:
    """Разница с удалением: архив забирает доступ, но не историю."""
    created = await create_account(client)
    await seed_history(created["id"])

    await client.post(f"{ACCOUNTS}/{created['id']}/archive")

    assert await scalar("select count(*) from deals where account_id = :id", id=created["id"]) == 2
    assert (
        await scalar("select count(*) from positions where account_id = :id", id=created["id"]) == 1
    )


async def test_archive_is_idempotent(client: AsyncClient) -> None:
    created = await create_account(client)
    await client.post(f"{ACCOUNTS}/{created['id']}/archive")

    response = await client.post(f"{ACCOUNTS}/{created['id']}/archive")

    assert response.status_code == 200
    assert response.json()["status"] == "archived"


@pytest.mark.parametrize("suffix", ["/pause", "/resume"])
async def test_archived_account_cannot_be_resumed(client: AsyncClient, suffix: str) -> None:
    created = await create_account(client)
    await client.post(f"{ACCOUNTS}/{created['id']}/archive")

    response = await client.post(f"{ACCOUNTS}/{created['id']}{suffix}")

    assert response.status_code == 422
    assert error_code(response) == "account_archived"


async def test_archived_account_cannot_be_edited(client: AsyncClient) -> None:
    """Иначе `PATCH` с паролем воскресил бы credentials у выведенного из работы счёта."""
    created = await create_account(client)
    await client.post(f"{ACCOUNTS}/{created['id']}/archive")

    response = await client.patch(f"{ACCOUNTS}/{created['id']}", json={"password": "новый"})

    assert response.status_code == 422
    assert error_code(response) == "account_archived"
    assert await credentials_rows(created["id"]) == 0


# --- удаление ----------------------------------------------------------------


async def test_delete_removes_the_account_with_everything_on_it(client: AsyncClient) -> None:
    """DoD S1-06: удаление каскадно чистит deals и positions.

    Вместе с позициями уходит и пользовательский слой — заметки, рефлексии, вложения.
    `CLAUDE.md` §2 защищает его от **пересборки** позиций, а не от явного удаления счёта;
    оставить заметки без позиций значило бы хранить мусор, на который ничто не ссылается.
    """
    created = await create_account(client)
    await seed_history(created["id"])

    response = await client.delete(f"{ACCOUNTS}/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    for table in ("deals", "positions", "sync_runs", "trading_accounts"):
        column = "id" if table == "trading_accounts" else "account_id"
        left = await scalar(f"select count(*) from {table} where {column} = :id", id=created["id"])
        assert left == 0, table
    for table in ("journal_entries", "reflections", "attachments"):
        assert await scalar(f"select count(*) from {table}") == 0, table
    assert await credentials_rows(created["id"]) == 0


async def test_delete_touches_nothing_else(client: AsyncClient) -> None:
    """Соседний счёт того же пользователя переживает удаление вместе со своей историей."""
    doomed = await create_account(client)
    survivor = await create_account(client, label="Второй", login=5001235)
    await seed_history(doomed["id"])
    await seed_history(survivor["id"])

    await client.delete(f"{ACCOUNTS}/{doomed['id']}")

    assert await scalar("select count(*) from deals where account_id = :id", id=survivor["id"]) == 2
    assert await scalar("select count(*) from journal_entries") == 1


async def test_delete_is_404_on_the_second_call(client: AsyncClient) -> None:
    created = await create_account(client)
    assert (await client.delete(f"{ACCOUNTS}/{created['id']}")).status_code == 204

    assert (await client.delete(f"{ACCOUNTS}/{created['id']}")).status_code == 404


# --- внеочередной синк -------------------------------------------------------


async def requested_at(account_id: str) -> Any:
    return await scalar(
        "select sync_requested_at from trading_accounts where id = :id", id=account_id
    )


async def test_sync_now_writes_the_mark_and_returns_a_receipt(client: AsyncClient) -> None:
    """202 и ровно четыре поля: просьба записана, синк выполнит коллектор (SPEC.md 8.2)."""
    created = await create_account(client)

    response = await client.post(f"{ACCOUNTS}/{created['id']}/sync-now")

    assert response.status_code == 202
    body = response.json()
    assert set(body) == {
        "sync_requested_at",
        "last_sync_at",
        "last_heartbeat_at",
        "collector_online",
    }
    assert body["sync_requested_at"].endswith("Z")
    assert body["last_sync_at"] is None
    # Коллектор к новому счёту ещё не приходил — обещать скорый синк нечем.
    assert body["collector_online"] is False
    assert await requested_at(created["id"]) is not None


async def test_repeated_sync_now_moves_the_mark_forward(client: AsyncClient) -> None:
    """Второй нажим — не конфликт: коллектор сравнивает метку с последним синком."""
    created = await create_account(client)

    first = await client.post(f"{ACCOUNTS}/{created['id']}/sync-now")
    second = await client.post(f"{ACCOUNTS}/{created['id']}/sync-now")

    assert second.status_code == 202
    assert second.json()["sync_requested_at"] > first.json()["sync_requested_at"]


@pytest.mark.parametrize(("heartbeat_age_minutes", "online"), [(1, True), (6, False)])
async def test_collector_online_follows_the_heartbeat(
    client: AsyncClient, heartbeat_age_minutes: int, online: bool
) -> None:
    """Порог из SPEC.md 9.3 — пять минут. Без этого поля UI сказал бы «синхронизировано»
    и на счёте, коллектор которого выключен неделю назад.
    """
    created = await create_account(client)
    await execute(
        "update trading_accounts "
        "set last_heartbeat_at = now() - make_interval(mins => :minutes), "
        "    last_sync_at = now() - interval '1 hour' "
        "where id = :id",
        id=created["id"],
        minutes=heartbeat_age_minutes,
    )

    body = (await client.post(f"{ACCOUNTS}/{created['id']}/sync-now")).json()

    assert body["collector_online"] is online
    assert body["last_heartbeat_at"].endswith("Z")
    assert body["last_sync_at"].endswith("Z")


async def test_paused_account_cannot_request_a_sync(client: AsyncClient) -> None:
    """422, а не тихое «принято»: счёта на паузе нет в выдаче assignments (SPEC.md 5.6),
    и прочитать просьбу физически некому.
    """
    created = await create_account(client)
    await client.post(f"{ACCOUNTS}/{created['id']}/pause")

    response = await client.post(f"{ACCOUNTS}/{created['id']}/sync-now")

    assert response.status_code == 422
    assert error_code(response) == "account_paused"
    assert await requested_at(created["id"]) is None


async def test_archived_account_cannot_request_a_sync(client: AsyncClient) -> None:
    created = await create_account(client)
    await client.post(f"{ACCOUNTS}/{created['id']}/archive")

    response = await client.post(f"{ACCOUNTS}/{created['id']}/sync-now")

    assert response.status_code == 422
    assert error_code(response) == "account_archived"
    assert await requested_at(created["id"]) is None


async def test_resume_lets_the_sync_be_requested_again(client: AsyncClient) -> None:
    """Отказ на паузе — состояние, а не приговор: возобновление снимает его."""
    created = await create_account(client)
    await client.post(f"{ACCOUNTS}/{created['id']}/pause")
    await client.post(f"{ACCOUNTS}/{created['id']}/resume")

    response = await client.post(f"{ACCOUNTS}/{created['id']}/sync-now")

    assert response.status_code == 202


# --- прогоны синка -----------------------------------------------------------


async def test_sync_runs_are_returned_newest_first(client: AsyncClient) -> None:
    created = await create_account(client)
    await execute(
        """
        insert into sync_runs (account_id, source, started_at, deals_received, error)
        values
            (:id, 'collector', now() - interval '2 hour', 10, null),
            (:id, 'collector', now() - interval '1 hour', 0, 'MT5: неверный пароль')
        """,
        id=created["id"],
    )

    response = await client.get(f"{ACCOUNTS}/{created['id']}/sync-runs")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["deals_received"] for item in items] == [0, 10]
    assert items[0]["error"] == "MT5: неверный пароль"
    assert items[0]["started_at"].endswith("Z")


async def test_sync_runs_of_an_account_without_history_are_empty(client: AsyncClient) -> None:
    created = await create_account(client)

    assert (await client.get(f"{ACCOUNTS}/{created['id']}/sync-runs")).json() == {"items": []}


async def test_sync_runs_are_capped_at_fifty(client: AsyncClient) -> None:
    """Курсора у этого списка нет, поэтому предел — единственное, что держит размер ответа.

    `sync_runs` растёт по строке на каждый прогон синка: у активного счёта их набегают
    тысячи, и снятый предел выдаёт их все одним ответом.
    """
    created = await create_account(client)
    # `deals_received` = возраст прогона в минутах: по нему видно, что отброшены самые
    # старые, а не первые попавшиеся.
    await execute(
        """
        insert into sync_runs (account_id, source, started_at, deals_received)
        select cast(:id as uuid), 'collector', now() - make_interval(mins => age), age
        from generate_series(1, cast(:count as integer)) as age
        """,
        id=created["id"],
        count=SPEC_SYNC_RUNS_LIMIT + 5,
    )

    items = (await client.get(f"{ACCOUNTS}/{created['id']}/sync-runs")).json()["items"]

    assert len(items) == SPEC_SYNC_RUNS_LIMIT
    assert [item["deals_received"] for item in items] == list(range(1, SPEC_SYNC_RUNS_LIMIT + 1))


# --- валидация на границе ----------------------------------------------------


async def test_mt5_without_server_is_400(client: AsyncClient) -> None:
    """Пароль перестал быть обязательным (`T-07`), сервер и логин — нет.

    Без них счёт нечем сопоставить с тем, что открыто в терминале: `GET assignments`
    отдаёт коллектору именно пару сервер+логин (SPEC.md 5.6).
    """
    body = {key: value for key, value in MT5_BODY.items() if key != "server"}

    response = await client.post(ACCOUNTS, json=body)

    assert response.status_code == 400
    assert error_code(response) == "validation_error"
    assert (await scalar("select count(*) from trading_accounts")) == 0


async def test_rejected_create_writes_nothing(client: AsyncClient) -> None:
    response = await client.post(ACCOUNTS, json={**MT5_BODY, "color": "#000000"})

    assert response.status_code == 400
    assert (await scalar("select count(*) from trading_accounts")) == 0
    assert (await scalar("select count(*) from account_credentials")) == 0


async def test_validation_error_does_not_echo_the_password(client: AsyncClient) -> None:
    """Присланное значение не возвращается: пока поле объявлено, во входе есть секрет."""
    response = await client.post(
        ACCOUNTS, json={**MT5_BODY, "login": -1, "password": INVESTOR_PASSWORD}
    )

    assert response.status_code == 400
    assert INVESTOR_PASSWORD not in response.text
