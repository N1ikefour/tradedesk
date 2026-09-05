"""Профиль пользователя против настоящих Postgres и Redis — DoD S0-08.

Вход выполняется настоящим потоком OTP, а не подставленной строкой в sessions: PATCH
меняет владельца сессии, и проверять это на выдуманной сессии нечестно.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Iterator
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
from app.core.db import get_engine
from app.core.redis import get_redis
from app.domains.users.schemas import DISPLAY_NAME_MAX_LENGTH, sorted_timezones

pytestmark = pytest.mark.integration

API = "/api/v1"
API_DIR = Path(__file__).resolve().parents[2]

ORIGIN = "http://test"
CLIENT_IP = "203.0.113.10"
EMAIL = "trader@example.test"
OTHER_EMAIL = "other@example.test"

USERS_ME = f"{API}/users/me"
AUTH_ME = f"{API}/auth/me"
TIMEZONES = f"{API}/users/timezones"

# Значения по умолчанию из SPEC.md 3.1 — тест обязан краснеть, если они разошлись с БД.
DEFAULT_TIMEZONE = "Europe/Moscow"
DEFAULT_DAY_BOUNDARY_HOUR = 0

_CODE_RE = re.compile(r"\b\d{6}\b")

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
    """Второй пользователь того же приложения: у него своя cookie и своя строка в users."""
    async with make_client(app) as opened:
        await login(opened, OTHER_EMAIL)
        yield opened


async def read_code(client: AsyncClient) -> str:
    response = await client.get(f"{API}/dev/outbox")
    assert response.status_code == 200
    found = _CODE_RE.search(response.json()["items"][0]["body_text"])
    assert found is not None
    return found.group()


async def login(client: AsyncClient, email: str) -> Response:
    assert (await client.post(f"{API}/auth/request-code", json={"email": email})).status_code == 202
    response = await client.post(
        f"{API}/auth/verify", json={"email": email, "code": await read_code(client)}
    )
    assert response.status_code == 200
    return response


async def row(email: str) -> tuple[Any, ...]:
    statement = text(
        "select display_name, timezone, day_boundary_hour from users where email = :email"
    )
    async with get_engine().connect() as connection:
        found = (await connection.execute(statement, {"email": email})).one()
    return tuple(found)


async def patch(client: AsyncClient, body: dict[str, Any]) -> Response:
    return await client.patch(USERS_ME, json=body)


def fields(response: Response) -> dict[str, str]:
    reported = response.json()["error"]
    assert reported["code"] == "validation_error"
    result = reported["details"]["fields"]
    assert isinstance(result, dict)
    return result


# --- чтение ------------------------------------------------------------------


async def test_get_me_returns_defaults_from_spec(client: AsyncClient) -> None:
    response = await client.get(USERS_ME)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == EMAIL
    assert body["display_name"] is None
    assert body["timezone"] == DEFAULT_TIMEZONE
    assert body["day_boundary_hour"] == DEFAULT_DAY_BOUNDARY_HOUR


async def test_get_me_matches_auth_me_body(client: AsyncClient) -> None:
    """Сравнение тел, а не утверждение о совпадении: у обоих маршрутов один пользователь."""
    await patch(client, {"display_name": "Ник", "timezone": "Asia/Tokyo", "day_boundary_hour": 9})

    users_me = await client.get(USERS_ME)
    auth_me = await client.get(AUTH_ME)

    assert users_me.status_code == auth_me.status_code == 200
    assert users_me.json() == auth_me.json()


# --- правка ------------------------------------------------------------------


async def test_patch_saves_all_fields(client: AsyncClient) -> None:
    response = await patch(
        client, {"display_name": "Ник", "timezone": "America/New_York", "day_boundary_hour": 17}
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Ник"
    assert response.json()["timezone"] == "America/New_York"
    assert response.json()["day_boundary_hour"] == 17
    assert await row(EMAIL) == ("Ник", "America/New_York", 17)


async def test_saved_values_survive_a_new_session(client: AsyncClient, app: FastAPI) -> None:
    """Проверка «сохранилось после перезагрузки»: значения читает другой вход того же лица."""
    await patch(client, {"display_name": "Ник", "timezone": "Asia/Tokyo", "day_boundary_hour": 9})

    async with make_client(app) as reopened:
        await login(reopened, EMAIL)
        response = await reopened.get(USERS_ME)

    assert response.json()["display_name"] == "Ник"
    assert response.json()["timezone"] == "Asia/Tokyo"
    assert response.json()["day_boundary_hour"] == 9


async def test_patch_keeps_fields_it_was_not_given(client: AsyncClient) -> None:
    await patch(
        client, {"display_name": "Ник", "timezone": "America/New_York", "day_boundary_hour": 17}
    )

    response = await patch(client, {"timezone": "Europe/Berlin"})

    assert response.status_code == 200
    assert await row(EMAIL) == ("Ник", "Europe/Berlin", 17)


async def test_empty_patch_changes_nothing(client: AsyncClient) -> None:
    await patch(client, {"display_name": "Ник", "timezone": "Asia/Tokyo", "day_boundary_hour": 9})

    response = await patch(client, {})

    assert response.status_code == 200
    assert await row(EMAIL) == ("Ник", "Asia/Tokyo", 9)


async def test_explicit_null_clears_display_name(client: AsyncClient) -> None:
    """`null` — операция «очистить», в отличие от отсутствия поля."""
    await patch(client, {"display_name": "Ник"})

    response = await patch(client, {"display_name": None})

    assert response.status_code == 200
    assert response.json()["display_name"] is None
    assert (await row(EMAIL))[0] is None


@pytest.mark.parametrize("raw", ["", "   ", "\n\t"])
async def test_blank_display_name_becomes_null(client: AsyncClient, raw: str) -> None:
    await patch(client, {"display_name": "Ник"})

    response = await patch(client, {"display_name": raw})

    assert response.status_code == 200
    assert response.json()["display_name"] is None
    assert (await row(EMAIL))[0] is None


async def test_display_name_is_trimmed(client: AsyncClient) -> None:
    response = await patch(client, {"display_name": "  Ник  "})

    assert response.json()["display_name"] == "Ник"
    assert (await row(EMAIL))[0] == "Ник"


# --- отказы ------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["UTC+3", "GMT+3", "MSK", "europe/moscow", "Europe/Moskva", ""])
async def test_unknown_timezone_is_400(client: AsyncClient, raw: str) -> None:
    response = await patch(client, {"timezone": raw})

    assert response.status_code == 400
    assert "body.timezone" in fields(response)
    assert await row(EMAIL) == (None, DEFAULT_TIMEZONE, DEFAULT_DAY_BOUNDARY_HOUR)


@pytest.mark.parametrize("raw", [-1, 24, 100])
async def test_day_boundary_hour_out_of_range_is_400(client: AsyncClient, raw: int) -> None:
    response = await patch(client, {"day_boundary_hour": raw})

    assert response.status_code == 400
    assert "body.day_boundary_hour" in fields(response)
    assert await row(EMAIL) == (None, DEFAULT_TIMEZONE, DEFAULT_DAY_BOUNDARY_HOUR)


async def test_too_long_display_name_is_400(client: AsyncClient) -> None:
    response = await patch(client, {"display_name": "я" * (DISPLAY_NAME_MAX_LENGTH + 1)})

    assert response.status_code == 400
    assert "body.display_name" in fields(response)
    assert (await row(EMAIL))[0] is None


async def test_rejected_patch_does_not_apply_the_valid_part(client: AsyncClient) -> None:
    """Тело валидируется целиком: одна неверная таймзона не должна пропустить имя в БД."""
    response = await patch(client, {"display_name": "Ник", "timezone": "UTC+3"})

    assert response.status_code == 400
    assert await row(EMAIL) == (None, DEFAULT_TIMEZONE, DEFAULT_DAY_BOUNDARY_HOUR)


async def test_unknown_field_is_400(client: AsyncClient) -> None:
    response = await patch(client, {"timeZone": "Asia/Tokyo"})

    assert response.status_code == 400
    assert await row(EMAIL) == (None, DEFAULT_TIMEZONE, DEFAULT_DAY_BOUNDARY_HOUR)


async def test_boolean_day_boundary_hour_is_400(client: AsyncClient) -> None:
    """`true` — ошибка клиента, а не час 1: bool наследует int, и без явного отказа
    мягкий режим pydantic сохранил бы его молча.
    """
    response = await patch(client, {"day_boundary_hour": True})

    assert response.status_code == 400
    assert "body.day_boundary_hour" in fields(response)
    assert await row(EMAIL) == (None, DEFAULT_TIMEZONE, DEFAULT_DAY_BOUNDARY_HOUR)


# --- список таймзон ----------------------------------------------------------


async def test_timezones_are_sorted_and_carry_the_canonical_names(client: AsyncClient) -> None:
    """Регресс: меню строилось из `Intl.supportedValuesOf`, где для Украины, Индии и
    Вьетнама есть только legacy-имена, а в tzdata образа — только канонические.
    """
    response = await client.get(TIMEZONES)

    assert response.status_code == 200
    items = response.json()["items"]
    assert items == sorted(items)
    assert {"Europe/Kyiv", "Asia/Kolkata", "Asia/Ho_Chi_Minh", "Europe/Moscow"} <= set(items)
    assert "localtime" not in items


async def test_every_offered_timezone_is_accepted_by_patch(client: AsyncClient) -> None:
    """Инвариант, который пропустил major: имя из выдачи маршрута обязано сохраняться.

    Проходится весь список, а не выборка: сломанными были 18 имён из четырёхсот, и любая
    выборка прошла бы мимо. Сверяется ответ `PATCH` — значит, имя прошло и валидацию, и
    запись, а не просто не упало.
    """
    items = (await client.get(TIMEZONES)).json()["items"]
    assert len(items) > 400

    rejected = []
    for name in items:
        response = await patch(client, {"timezone": name})
        if response.status_code != 200 or response.json()["timezone"] != name:
            rejected.append((name, response.status_code))

    assert rejected == []
    assert (await row(EMAIL))[1] == items[-1]


async def test_timezones_revalidation_is_cheap(client: AsyncClient) -> None:
    """Список большой и меняется только с образом: клиент держит его до смены ETag.

    `no-cache` вместо `max-age`: устаревшее меню предложило бы имя, которое сервер уже
    не принимает, — ровно та поломка, ради которой маршрут появился.
    """
    first = await client.get(TIMEZONES)

    assert first.headers["cache-control"] == "private, no-cache"
    etag = first.headers["etag"]
    assert etag.startswith('"')

    second = await client.get(TIMEZONES, headers={"if-none-match": etag})

    assert second.status_code == 304
    assert second.content == b""
    assert second.headers["etag"] == etag
    assert (await client.get(TIMEZONES, headers={"if-none-match": '"stale"'})).status_code == 200
    # RFC 9110 §13.1.2: `*` — «отдай, только если у тебя ничего нет», и представление есть.
    assert (await client.get(TIMEZONES, headers={"if-none-match": "*"})).status_code == 304


async def test_timezones_body_matches_the_validated_set(client: AsyncClient) -> None:
    """Маршрут и валидация читают один набор — разъехаться им негде."""
    response = await client.get(TIMEZONES)

    assert response.json()["items"] == list(sorted_timezones())


# --- границы владельца -------------------------------------------------------


async def test_patch_changes_only_the_session_owner(
    client: AsyncClient, other_client: AsyncClient
) -> None:
    await patch(client, {"display_name": "Ник", "timezone": "Asia/Tokyo", "day_boundary_hour": 9})

    assert await row(EMAIL) == ("Ник", "Asia/Tokyo", 9)
    assert await row(OTHER_EMAIL) == (None, DEFAULT_TIMEZONE, DEFAULT_DAY_BOUNDARY_HOUR)
    assert (await other_client.get(USERS_ME)).json()["email"] == OTHER_EMAIL


async def test_patch_after_logout_is_401(client: AsyncClient) -> None:
    assert (await client.post(f"{API}/auth/logout")).status_code == 204

    response = await patch(client, {"timezone": "Asia/Tokyo"})

    assert response.status_code == 401
    assert await row(EMAIL) == (None, DEFAULT_TIMEZONE, DEFAULT_DAY_BOUNDARY_HOUR)
