"""Поток входа целиком против настоящих Postgres и Redis — DoD S0-04.

Ни база, ни Redis не мокаются: проверяются ровно те SQL и счётчики, которые поедут в прод.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from app.core.redis import close_redis, get_redis
from app.domains.auth import service as auth_service
from app.domains.auth.cookies import SESSION_COOKIE_NAME

pytestmark = pytest.mark.integration

API = "/api/v1"
API_DIR = Path(__file__).resolve().parents[2]

ORIGIN = "http://test"
CLIENT_IP = "203.0.113.10"
# Адрес «прокси» в тестах X-06: тот же смысл, что у web/caddy в docker-compose.yml.
PROXY_IP = "10.87.0.10"
EMAIL = "trader@example.test"

_CODE_RE = re.compile(r"\b\d{6}\b")

# Числа из SPEC.md 4, а не из констант приложения: тест обязан краснеть, когда
# лимит в коде разошёлся со спецификацией.
MAX_ATTEMPTS = 5
EMAIL_LIMIT = 3
EMAIL_WINDOW_SECONDS = 10 * 60
IP_LIMIT = 10
IP_WINDOW_SECONDS = 60 * 60
# Max-Age cookie: 30 суток из SPEC.md 4, пункт 3.
SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60

# Таблицы, которые наполняет этот тест. TRUNCATE между тестами дешевле, чем миграция.
_TABLES = "users, otp_codes, sessions, dev_outbox"


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
    """Миграции накатываются один раз на модуль: между тестами чистятся только данные."""
    url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("APP_ENV", "local")
        monkeypatch.setenv("DATABASE_URL", url)
        config = Config(str(API_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(API_DIR / "alembic"))
        command.upgrade(config, "head")
        yield
        command.downgrade(config, "base")


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
    """Каждый тест стартует с пустых таблиц и пустого Redis: лимиты не текут между тестами."""
    async with get_engine().begin() as connection:
        await connection.execute(text(f"truncate {_TABLES} cascade"))
    await get_redis().flushdb()
    yield


def make_client(
    app: FastAPI, ip: str = CLIENT_IP, raise_app_exceptions: bool = True
) -> AsyncClient:
    """Origin проставлен по умолчанию: так ходит браузер, и так работает проверка CSRF.

    `raise_app_exceptions=False` нужен там, где проверяется ответ на необработанное
    исключение: Starlette отдаёт 500 и следом перебрасывает исключение наверх.
    """
    transport = ASGITransport(
        app=app, client=(ip, 51234), raise_app_exceptions=raise_app_exceptions
    )
    return AsyncClient(transport=transport, base_url=ORIGIN, headers={"origin": ORIGIN})


def proxied_app(live_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]) -> FastAPI:
    """Приложение, которому разрешено верить X-Forwarded-For от `PROXY_IP` (X-06)."""
    live_env.setenv("TRUSTED_PROXIES", PROXY_IP)
    # Конфиг — синглтон, а движок и Redis уже созданы фикстурой clean_state на старых
    # настройках. Хранилища в них те же, меняется только TRUSTED_PROXIES.
    get_settings.cache_clear()
    return make_app()


def make_proxied_client(app: FastAPI, ip: str) -> AsyncClient:
    """Браузер с адресом `ip`, ходящий через доверенный прокси, — топология профиля local."""
    client = make_client(app, ip=PROXY_IP)
    client.headers["x-forwarded-for"] = ip
    return client


async def kill_redis(live_env: pytest.MonkeyPatch) -> None:
    """Redis смотрит в закрытый порт: недоступность без ожидания сети."""
    live_env.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    get_settings.cache_clear()
    await close_redis()


@pytest.fixture
async def client(
    live_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> AsyncIterator[AsyncClient]:
    async with make_client(make_app()) as client:
        yield client


async def fetch_all(sql: str) -> list[Any]:
    async with get_engine().connect() as connection:
        return list((await connection.execute(text(sql))).all())


async def execute(sql: str) -> None:
    async with get_engine().begin() as connection:
        await connection.execute(text(sql))


async def request_code(client: AsyncClient, email: str = EMAIL) -> Response:
    return await client.post(f"{API}/auth/request-code", json={"email": email})


async def read_code(client: AsyncClient) -> str:
    """Код добывается ровно так же, как его достанет разработчик: со страницы /dev/outbox."""
    response = await client.get(f"{API}/dev/outbox")
    assert response.status_code == 200
    found = _CODE_RE.search(response.json()["items"][0]["body_text"])
    assert found is not None
    return found.group()


async def verify(client: AsyncClient, code: str, email: str = EMAIL) -> Response:
    return await client.post(f"{API}/auth/verify", json={"email": email, "code": code})


async def login(client: AsyncClient, email: str = EMAIL) -> Response:
    assert (await request_code(client, email)).status_code == 202
    return await verify(client, await read_code(client), email)


def wrong_code(code: str) -> str:
    return "000000" if code != "000000" else "111111"


def session_cookie(response: Response) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{SESSION_COOKIE_NAME}="):
            return header
    return None


# --- request-code ------------------------------------------------------------


async def test_request_code_returns_202_and_creates_nothing_but_the_code(
    client: AsyncClient,
) -> None:
    response = await request_code(client)

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    # Пользователь заводится на verify: неудачный запрос кода не должен плодить записи.
    assert await fetch_all("select id from users") == []
    assert len(await fetch_all("select id from otp_codes")) == 1


async def test_request_code_is_indistinguishable_for_known_and_unknown_email(
    client: AsyncClient,
) -> None:
    """SPEC.md 4: эндпоинт не должен перечислять зарегистрированные адреса."""
    unknown = await request_code(client, "nobody@example.test")
    assert (await login(client)).status_code == 200

    known = await request_code(client, EMAIL)

    assert (unknown.status_code, unknown.json()) == (known.status_code, known.json())


async def test_code_lands_in_dev_outbox(client: AsyncClient) -> None:
    await request_code(client)

    items = (await client.get(f"{API}/dev/outbox")).json()["items"]

    assert len(items) == 1
    assert items[0]["to_email"] == EMAIL
    assert _CODE_RE.search(items[0]["body_text"]) is not None


async def test_outbox_returns_newest_first(client: AsyncClient) -> None:
    await request_code(client, "first@example.test")
    await request_code(client, "second@example.test")

    items = (await client.get(f"{API}/dev/outbox")).json()["items"]

    assert [item["to_email"] for item in items] == ["second@example.test", "first@example.test"]


async def test_code_is_stored_only_as_hash(client: AsyncClient) -> None:
    await request_code(client)
    code = await read_code(client)

    rows = await fetch_all("select code_hash from otp_codes")

    assert code not in rows[0][0]
    assert len(rows[0][0]) == 64


# --- verify ------------------------------------------------------------------


async def test_verify_creates_user_and_sets_cookie(client: AsyncClient) -> None:
    await request_code(client)

    response = await verify(client, await read_code(client))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "email", "display_name", "timezone", "day_boundary_hour"}
    assert body["email"] == EMAIL
    assert body["timezone"] == "Europe/Moscow"
    assert body["day_boundary_hour"] == 0

    cookie = session_cookie(response)
    assert cookie is not None
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie.replace("samesite", "SameSite")
    assert "Path=/" in cookie
    assert f"Max-Age={SESSION_MAX_AGE_SECONDS}" in cookie
    # APP_ENV=local: Secure на http://localhost браузер отбросил бы вместе с cookie.
    assert "Secure" not in cookie

    sessions = await fetch_all("select id, user_id, user_agent from sessions")
    assert len(sessions) == 1
    assert str(sessions[0][0]) == client.cookies[SESSION_COOKIE_NAME]


async def test_session_id_is_not_time_ordered(client: AsyncClient) -> None:
    """uuid4, а не uuid7: значение cookie не должно раскрывать время создания сессии."""
    await login(client)

    (session_id,) = (await fetch_all("select id from sessions"))[0]

    assert session_id.version == 4


async def test_second_login_reuses_the_user(client: AsyncClient) -> None:
    await login(client)
    await client.post(f"{API}/auth/logout")

    await login(client, EMAIL.upper())

    assert len(await fetch_all("select id from users")) == 1


async def test_used_code_does_not_work_twice(client: AsyncClient) -> None:
    await request_code(client)
    code = await read_code(client)
    assert (await verify(client, code)).status_code == 200

    response = await verify(client, code)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_code"


async def test_five_wrong_codes_burn_the_code(client: AsyncClient) -> None:
    """DoD S0-04: после пяти неверных попыток верный код уже не пускает."""
    await request_code(client)
    code = await read_code(client)
    bad = wrong_code(code)

    for attempt in range(1, MAX_ATTEMPTS):
        response = await verify(client, bad)
        assert response.status_code == 422, attempt
        assert response.json()["error"]["code"] == "invalid_code", attempt

    last = await verify(client, bad)
    assert last.status_code == 422
    assert last.json()["error"]["code"] == "too_many_attempts"

    after = await verify(client, code)
    assert after.status_code == 422
    assert after.json()["error"]["code"] == "invalid_code"
    assert session_cookie(after) is None
    assert await fetch_all("select id from sessions") == []
    assert await fetch_all("select id from users") == []

    (attempts, consumed_at) = (await fetch_all("select attempts, consumed_at from otp_codes"))[0]
    assert attempts == MAX_ATTEMPTS
    assert consumed_at is not None


async def test_expired_code_is_rejected(client: AsyncClient) -> None:
    await request_code(client)
    code = await read_code(client)
    await execute("update otp_codes set expires_at = now() - interval '1 second'")

    response = await verify(client, code)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_code"
    # Просроченный код не гасится и не увеличивает счётчик: он просто не подходит.
    assert (await fetch_all("select attempts from otp_codes"))[0][0] == 0


async def test_newest_code_wins(client: AsyncClient) -> None:
    """Проверяется последний непогашенный код (SPEC.md 4): предыдущий уже не подходит."""
    await request_code(client)
    old = await read_code(client)
    await request_code(client)
    new = await read_code(client)
    assert old != new

    assert (await verify(client, old)).status_code == 422
    assert (await verify(client, new)).status_code == 200


async def test_verify_from_foreign_origin_changes_nothing(client: AsyncClient) -> None:
    await request_code(client)
    code = await read_code(client)

    response = await client.post(
        f"{API}/auth/verify",
        json={"email": EMAIL, "code": code},
        headers={"origin": "http://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden_origin"
    assert await fetch_all("select id from sessions") == []
    assert (await fetch_all("select attempts from otp_codes"))[0][0] == 0


# --- me / logout -------------------------------------------------------------


async def test_me_returns_profile_for_live_session(client: AsyncClient) -> None:
    logged_in = await login(client)

    response = await client.get(f"{API}/auth/me")

    assert response.status_code == 200
    assert response.json() == logged_in.json()


async def test_me_without_cookie_is_401(client: AsyncClient) -> None:
    response = await client.get(f"{API}/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_me_with_unknown_session_is_401(client: AsyncClient) -> None:
    await login(client)
    await execute("delete from sessions")

    response = await client.get(f"{API}/auth/me")

    assert response.status_code == 401


async def test_expired_session_is_401(client: AsyncClient) -> None:
    await login(client)
    await execute("update sessions set expires_at = now() - interval '1 second'")

    response = await client.get(f"{API}/auth/me")

    assert response.status_code == 401


async def test_logout_removes_session_and_clears_cookie(client: AsyncClient) -> None:
    await login(client)

    response = await client.post(f"{API}/auth/logout")

    assert response.status_code == 204
    assert session_cookie(response) is not None
    assert await fetch_all("select id from sessions") == []
    assert (await client.get(f"{API}/auth/me")).status_code == 401
    # Клиент действительно перестал слать cookie, а не только сервер перестал её знать.
    assert SESSION_COOKIE_NAME not in client.cookies


async def test_logout_is_idempotent(client: AsyncClient) -> None:
    await login(client)

    assert (await client.post(f"{API}/auth/logout")).status_code == 204
    assert (await client.post(f"{API}/auth/logout")).status_code == 204


async def test_logout_does_not_touch_other_sessions(
    client: AsyncClient, live_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> None:
    await login(client)
    async with make_client(make_app()) as second:
        await login(second, "another@example.test")

        await client.post(f"{API}/auth/logout")

        assert (await second.get(f"{API}/auth/me")).status_code == 200


# --- скользящее продление ----------------------------------------------------


async def test_session_is_extended_when_last_seen_is_old(client: AsyncClient) -> None:
    await login(client)
    await execute(
        "update sessions set last_seen_at = now() - interval '2 days', "
        "expires_at = now() + interval '28 days'"
    )
    (before,) = (await fetch_all("select expires_at from sessions"))[0]

    response = await client.get(f"{API}/auth/me")

    assert response.status_code == 200
    (last_seen_at, expires_at) = (await fetch_all("select last_seen_at, expires_at from sessions"))[
        0
    ]
    assert (datetime.now(UTC) - last_seen_at).total_seconds() < 60
    assert expires_at > before
    # Cookie переставляется вместе с продлением, иначе браузер выбросит её раньше срока.
    assert session_cookie(response) is not None


async def test_session_is_not_touched_when_last_seen_is_fresh(client: AsyncClient) -> None:
    await login(client)
    (before,) = (await fetch_all("select last_seen_at from sessions"))[0]

    response = await client.get(f"{API}/auth/me")

    assert response.status_code == 200
    assert (await fetch_all("select last_seen_at from sessions"))[0][0] == before
    assert session_cookie(response) is None


# --- rate-limit --------------------------------------------------------------


async def test_rate_limit_per_email(
    client: AsyncClient, live_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> None:
    """3 запроса / 10 минут на адрес — независимо от того, с какого IP они пришли."""
    for _ in range(EMAIL_LIMIT):
        assert (await request_code(client)).status_code == 202

    async with make_client(make_app(), ip="198.51.100.7") as other_ip:
        response = await request_code(other_ip)

    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "rate_limited"
    assert 0 < body["error"]["details"]["retry_after"] <= EMAIL_WINDOW_SECONDS
    assert response.headers["retry-after"] == str(body["error"]["details"]["retry_after"])
    # Заблокированный запрос не создаёт код и не шлёт письмо.
    assert len(await fetch_all("select id from otp_codes")) == EMAIL_LIMIT


async def test_rate_limit_per_ip(client: AsyncClient) -> None:
    """10 запросов / час на IP — считаются поверх разных адресов."""
    for index in range(IP_LIMIT):
        response = await request_code(client, f"user{index}@example.test")
        assert response.status_code == 202, index

    response = await request_code(client, "one-too-many@example.test")

    assert response.status_code == 429
    assert 0 < response.json()["error"]["details"]["retry_after"] <= IP_WINDOW_SECONDS
    assert len(await fetch_all("select id from otp_codes")) == IP_LIMIT


# --- X-06: лимит по IP за прокси ---------------------------------------------


async def test_proxy_does_not_merge_users_into_one_limit(
    live_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> None:
    """Ровно прогон ревью S0-04: 12 пользователей через один прокси — и ни одного 429.

    До X-06 все они приходили с адреса прокси, лимит становился общим на установку,
    и блокировался одиннадцатый **пользователь**.
    """
    app = proxied_app(live_env, make_app)

    for index in range(12):
        async with make_proxied_client(app, ip=f"203.0.113.{index + 1}") as browser:
            response = await request_code(browser, f"user{index}@example.test")
        assert response.status_code == 202, index

    assert len(await fetch_all("select id from otp_codes")) == 12


async def test_forged_forwarded_for_does_not_move_the_limit(
    live_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> None:
    """Заголовок от недоверенного источника — просто текст: лимит считается по соединению."""
    app = proxied_app(live_env, make_app)
    forger = "198.51.100.66"

    for index in range(IP_LIMIT):
        # Каждый запрос представляется новым адресом — без проверки источника это давало бы
        # свежий лимит на каждый запрос.
        async with make_client(app, ip=forger) as direct:
            direct.headers["x-forwarded-for"] = f"203.0.113.{index + 1}"
            assert (await request_code(direct, f"forged{index}@example.test")).status_code == 202

    async with make_client(app, ip=forger) as direct:
        direct.headers["x-forwarded-for"] = "203.0.113.200"
        response = await request_code(direct, "one-too-many@example.test")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


async def test_ip_limit_does_not_spend_the_email_limit(
    live_env: pytest.MonkeyPatch, make_app: Callable[[], FastAPI]
) -> None:
    """Порядок проверок: отбитый общим лимитом запрос не жжёт личную квоту пользователя.

    Соседи по адресу выбирают лимит по IP; жертва упирается в него, ничего не сделав.
    Её три запроса в 10 минут обязаны остаться нетронутыми — проверяем с другого адреса.
    """
    app = proxied_app(live_env, make_app)
    crowded = "203.0.113.50"
    victim = "victim@example.test"

    for index in range(IP_LIMIT):
        async with make_proxied_client(app, ip=crowded) as neighbour:
            response = await request_code(neighbour, f"neighbour{index}@example.test")
        assert response.status_code == 202, index

    for _ in range(5):
        async with make_proxied_client(app, ip=crowded) as blocked:
            assert (await request_code(blocked, victim)).status_code == 429

    async with make_proxied_client(app, ip="203.0.113.51") as elsewhere:
        codes = [
            (await request_code(elsewhere, victim)).status_code for _ in range(EMAIL_LIMIT + 1)
        ]

    assert codes == [202] * EMAIL_LIMIT + [429]


# --- логи --------------------------------------------------------------------


async def test_logs_never_contain_code_email_or_hash(
    live_env: pytest.MonkeyPatch,
    make_app: Callable[[], FastAPI],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DoD S0-04: проверяется реальный вывод, а не рассуждение о нём."""
    email = "log.probe@example.test"
    async with make_client(make_app()) as client:
        await request_code(client, email)
        code = await read_code(client)
        await verify(client, wrong_code(code), email)
        await verify(client, code, email)
        await client.get(f"{API}/auth/me")
        await client.post(f"{API}/auth/logout")

    (code_hash,) = (await fetch_all("select code_hash from otp_codes"))[0]
    output = capsys.readouterr().out

    # Контроль самой проверки: без этой строки тест зеленел бы на пустом выводе.
    assert "mail.sent" in output
    assert code not in output
    assert email not in output
    assert code_hash not in output


# --- конкуренция ---------------------------------------------------------------


async def test_parallel_wrong_codes_cannot_outrun_the_attempt_limit(client: AsyncClient) -> None:
    """`with_for_update` в `_active_code`: без блокировки лимит пяти попыток обходится
    простой параллельностью — часть инкрементов `attempts` теряется, код не гасится,
    и перебор шестизначного кода перестаёт быть ограниченным."""
    await request_code(client)
    code = await read_code(client)
    bad = wrong_code(code)

    responses = await asyncio.gather(*(verify(client, bad) for _ in range(10)))

    assert {response.status_code for response in responses} == {422}
    (attempts, consumed_at) = (await fetch_all("select attempts, consumed_at from otp_codes"))[0]
    assert attempts == MAX_ATTEMPTS
    assert consumed_at is not None

    after = await verify(client, code)
    assert after.status_code == 422
    assert after.json()["error"]["code"] == "invalid_code"
    assert await fetch_all("select id from sessions") == []


# --- недоступный Redis ---------------------------------------------------------


async def test_dead_redis_blocks_sending_the_code(
    client: AsyncClient, live_env: pytest.MonkeyPatch
) -> None:
    """Fail-closed: неучтённый запрос кода снимает потолок и с писем, и с числа догадок."""
    await kill_redis(live_env)

    response = await request_code(client)

    assert response.status_code == 429
    body = response.json()
    assert body["error"]["code"] == "rate_limited"
    retry_after = body["error"]["details"]["retry_after"]
    assert retry_after > 0
    assert response.headers["retry-after"] == str(retry_after)
    # Ни кода, ни письма: 202 без отправки пользователь принял бы за потерянное письмо.
    assert await fetch_all("select id from otp_codes") == []
    assert await fetch_all("select id from dev_outbox") == []


async def test_dead_redis_does_not_break_verify_and_me(
    client: AsyncClient, live_env: pytest.MonkeyPatch
) -> None:
    """Redis участвует только в выпуске кода — вход по уже выданному коду от него не зависит."""
    await request_code(client)
    code = await read_code(client)
    await kill_redis(live_env)

    verified = await verify(client, code)
    me = await client.get(f"{API}/auth/me")
    logged_out = await client.post(f"{API}/auth/logout")

    assert verified.status_code == 200
    assert me.status_code == 200
    assert logged_out.status_code == 204


# --- логи на пути ошибки -------------------------------------------------------


async def test_database_error_does_not_leak_code_or_email_into_logs(
    live_env: pytest.MonkeyPatch,
    make_app: Callable[[], FastAPI],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Успешный поток ничего не печатает — а упавший запрос печатает traceback целиком,
    и SQLAlchemy вкладывает в текст `StatementError` все bound parameters: адрес,
    тему и тело письма с кодом внутри. Закрыто `hide_parameters` в core/db.py."""
    email = "leak.probe@example.test"
    code = "445341"
    monkeypatch.setattr(auth_service, "generate_code", lambda: code)
    await execute("alter table dev_outbox add constraint ck_probe_always_fails check (false)")
    try:
        async with make_client(make_app(), raise_app_exceptions=False) as client:
            response = await request_code(client, email)
    finally:
        await execute("alter table dev_outbox drop constraint ck_probe_always_fails")

    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "internal_error",
        "message": "Внутренняя ошибка сервера",
        "details": {},
    }
    output = capsys.readouterr().out
    # Контроль проверки: traceback обязан быть в выводе, иначе тест зеленел бы впустую.
    assert "api.unhandled_exception" in output
    assert "INSERT INTO dev_outbox" in output
    assert code not in output
    assert email not in output


async def test_database_error_text_carries_no_bound_parameters() -> None:
    """Второй рубеж, отдельно от логгера: `hide_parameters` в движке.

    Обработчик выше traceback ошибки БД больше не печатает, поэтому сам флаг ничем
    не проверялся бы. А он нужен: текст исключения стрингифицируют и в других местах.
    """
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.domains.mail.models import DevOutboxEntry

    await execute("alter table dev_outbox add constraint ck_probe_always_fails check (false)")
    try:
        async with AsyncSession(get_engine()) as session:
            session.add(
                DevOutboxEntry(
                    to_email=EMAIL,
                    subject="TradeDesk: код для входа",
                    body_text="Код для входа в TradeDesk: 445341",
                    body_html=None,
                )
            )
            with pytest.raises(IntegrityError) as error:
                await session.flush()
    finally:
        await execute("alter table dev_outbox drop constraint ck_probe_always_fails")

    message = str(error.value)
    assert "hide_parameters" in message
    assert "[parameters:" not in message
