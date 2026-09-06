"""Аналитика против настоящих Postgres и Redis — DoD S2-05.

Три группы. Первая — сводка: пример из `docs/metrics.md` §4 проезжает через живой SQL и
приходит теми же числами, что посчитаны на бумаге, а разница с суммой колонки журнала
равна ровно открытым позициям (§1.1 документа). Вторая — торговый день: примеры §2.4,
переход на летнее время и свойство «дни месяца покрывают время без дыр и пересечений»,
проверенное на зонах, где это ломается — `Pacific/Chatham` со сдвигом +12:45 и
`America/Santiago` с переводом в полночь. Третья — `daily_stats`: кэш обязан совпадать с
источником, иначе таблица, которую никто не читает, тихо разойдётся с календарём.

Главный тест здесь — `test_calendar_bounds_open_the_same_day_in_the_journal`. Он закрывает
дефект, ради которого правило дня вообще вынесено на сервер: календарь показывает сделку в
понедельник, а журнал за понедельник её не находит. Границы дня берутся из ответа
календаря и подставляются в фильтр журнала как есть — если они разойдутся с группировкой,
суммы не сойдутся.

`positions` до `S1-03` не наполняет никто, поэтому строки вставляются напрямую; форма
строки взята из `SPEC.md` 3.3 и миграции `b07a46275bbc`. **На настоящих данных MT5 это не
проверялось и проверено быть не может** — сборщика позиций ещё нет.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise
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
from app.core.db import get_engine, get_session_factory
from app.core.redis import get_redis
from app.domains.analytics import daily_stats
from app.domains.analytics.trading_day import DAYS_CTE

pytestmark = pytest.mark.integration

API = "/api/v1"
API_DIR = Path(__file__).resolve().parents[2]

ORIGIN = "http://test"
CLIENT_IP = "203.0.113.12"
EMAIL = "analytics@example.test"
OTHER_EMAIL = "stranger-analytics@example.test"

SUMMARY = f"{API}/analytics/summary"
CALENDAR = f"{API}/journal/calendar"
POSITIONS = f"{API}/journal/positions"
ACCOUNTS = f"{API}/accounts"
USERS_ME = f"{API}/users/me"

MT5_BODY: dict[str, Any] = {
    "label": "Демо FTMO",
    "platform": "mt5",
    "is_demo": True,
    "server": "FTMO-Demo",
    "login": 7101234,
    "password": "s3cret-investor-pw-9f21ac",
}

_CODE_RE = re.compile(r"\b\d{6}\b")

_TABLES = (
    "users, otp_codes, sessions, dev_outbox, trading_accounts, account_credentials, "
    "deals, positions, sync_runs, journal_entries, reflections, attachments, tags, daily_stats"
)

# Момент внутри торгового дня 2026-09-02 при любой зоне из примеров ниже.
MOMENT = datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC)

# Восемь закрытых позиций из `docs/metrics.md` §4: (gross_pnl, commission, swap, fee).
EXAMPLE_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("120.00", "-3.00", "-1.00", "0.00"),
    ("60.00", "-2.00", "0.00", "0.00"),
    ("40.00", "-4.00", "-2.00", "-1.00"),
    ("12.00", "-2.00", "0.00", "0.00"),
    ("-30.00", "-3.00", "-1.00", "0.00"),
    ("-50.00", "-2.00", "0.00", "0.00"),
    ("-10.00", "-4.00", "0.00", "0.00"),
    ("2.50", "-2.00", "-0.50", "0.00"),
)

# Открытые позиции того же периода: накопленная комиссия входа, а не результат.
EXAMPLE_OPEN = ("-1.20", "-0.80")

EXPECTED_SUMMARY: dict[str, Any] = {
    "trades": 8,
    "wins": 4,
    "losses": 3,
    "breakeven": 1,
    "open_positions": 2,
    "winrate": "0.5000",
    "net_pnl": "117.00",
    "gross_pnl": "144.50",
    "commission": "-22.00",
    "swap": "-4.50",
    "fee": "-1.00",
    "profit_factor": "2.17",
    "avg_win": "54.25",
    "avg_loss": "-33.33",
    "expectancy": "14.63",
    "best_trade": "116.00",
    "worst_trade": "-52.00",
}

_POSITION_COLUMNS = (
    "id",
    "account_id",
    "position_id",
    "symbol_raw",
    "symbol_norm",
    "direction",
    "status",
    "open_time",
    "close_time",
    "volume_opened",
    "volume_closed",
    "avg_entry_price",
    "avg_exit_price",
    "gross_pnl",
    "commission",
    "swap",
    "fee",
    "net_pnl",
    "deals_count",
    "duration_seconds",
    "close_reason",
    "is_manual",
    "rebuilt_at",
)

_INSERT_POSITION = (
    f"insert into positions ({', '.join(_POSITION_COLUMNS)}) "
    f"values ({', '.join(':' + name for name in _POSITION_COLUMNS)})"
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
    """Миграции — один раз на модуль; между тестами чистятся только данные."""
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


async def execute(statement: str, **params: Any) -> None:
    async with get_engine().begin() as connection:
        await connection.execute(text(statement), params)


_next_broker_id = iter(range(2000, 200000))


async def create_account(client: AsyncClient, **overrides: Any) -> str:
    # Логин уникален у каждого счёта: `unique (user_id, platform, server, login)`.
    body = {**MT5_BODY, "login": next(_next_broker_id), **overrides}
    response = await client.post(ACCOUNTS, json=body)
    assert response.status_code == 201, response.text
    account_id = response.json()["id"]
    assert isinstance(account_id, str)
    return account_id


@pytest.fixture
async def account(client: AsyncClient) -> str:
    return await create_account(client)


async def set_day_rule(client: AsyncClient, timezone: str, boundary_hour: int) -> None:
    """Зона и граница дня — через настоящий `PATCH /users/me`, а не правкой строки."""
    response = await client.patch(
        USERS_ME, json={"timezone": timezone, "day_boundary_hour": boundary_hour}
    )
    assert response.status_code == 200, response.text


async def seed_position(account_id: str, **overrides: Any) -> UUID:
    """Одна закрытая позиция со значениями по умолчанию; отличается только тем, что задано."""
    identifier = overrides.pop("id", None) or uuid4()
    close_time = overrides.pop("close_time", MOMENT)
    row: dict[str, Any] = {
        "id": identifier,
        "account_id": UUID(account_id),
        "position_id": next(_next_broker_id),
        "symbol_raw": "EURUSD.m",
        "symbol_norm": "EURUSD",
        "direction": "long",
        "status": "closed",
        "open_time": (close_time or MOMENT) - timedelta(hours=1),
        "close_time": close_time,
        "volume_opened": Decimal("0.10"),
        "volume_closed": Decimal("0.10"),
        "avg_entry_price": Decimal("1.08543000"),
        "avg_exit_price": Decimal("1.08643000"),
        "gross_pnl": Decimal("10.35"),
        "commission": Decimal("-0.35"),
        "swap": Decimal("0.00"),
        "fee": Decimal("0.00"),
        "net_pnl": Decimal("10.00"),
        "deals_count": 2,
        "duration_seconds": 3600,
        "close_reason": "tp",
        "is_manual": False,
        "rebuilt_at": MOMENT,
    }
    row.update(overrides)
    await execute(_INSERT_POSITION, **row)
    assert isinstance(identifier, UUID)
    return identifier


async def seed_open_position(account_id: str, net_pnl: str, **overrides: Any) -> UUID:
    return await seed_position(
        account_id,
        status="open",
        close_time=None,
        duration_seconds=None,
        avg_exit_price=None,
        volume_closed=Decimal("0"),
        close_reason=None,
        gross_pnl=Decimal("0.00"),
        commission=Decimal(net_pnl),
        net_pnl=Decimal(net_pnl),
        **overrides,
    )


async def seed_worked_example(account_id: str, close_time: datetime = MOMENT) -> None:
    """Восемь закрытых позиций и две открытые — таблица `docs/metrics.md` §4."""
    for gross, commission, swap, fee in EXAMPLE_ROWS:
        net = Decimal(gross) + Decimal(commission) + Decimal(swap) + Decimal(fee)
        await seed_position(
            account_id,
            close_time=close_time,
            gross_pnl=Decimal(gross),
            commission=Decimal(commission),
            swap=Decimal(swap),
            fee=Decimal(fee),
            net_pnl=net,
        )
    for open_net in EXAMPLE_OPEN:
        await seed_open_position(account_id, open_net, open_time=close_time)


def error_code(response: Response) -> str:
    code = response.json()["error"]["code"]
    assert isinstance(code, str)
    return code


# --- сводка --------------------------------------------------------------------


@pytest.mark.parametrize("field", sorted(EXPECTED_SUMMARY))
async def test_summary_matches_the_worked_example(
    client: AsyncClient, account: str, field: str
) -> None:
    """Пример из документа через живой SQL — те же числа, что посчитаны на бумаге."""
    await seed_worked_example(account)

    response = await client.get(SUMMARY)

    assert response.status_code == 200, response.text
    assert response.json()[field] == EXPECTED_SUMMARY[field]


async def test_the_difference_with_the_journal_column_is_exactly_the_open_positions(
    client: AsyncClient, account: str
) -> None:
    """`docs/metrics.md` §1.1: расхождение шапки и колонки известно и объяснимо.

    Это то, что заметит первый же человек, сложивший колонку на экране. Здесь оно
    зафиксировано числом: разница равна сумме открытых позиций, а `open_positions`
    показывает, сколько их.
    """
    await seed_worked_example(account)

    summary = (await client.get(SUMMARY)).json()
    listed = (await client.get(POSITIONS, params={"limit": 200})).json()["items"]
    column = sum((Decimal(item["net_pnl"]) for item in listed), Decimal(0))
    open_rows = sum(
        (Decimal(item["net_pnl"]) for item in listed if item["status"] == "open"), Decimal(0)
    )

    assert column == Decimal("115.00")
    assert Decimal(summary["net_pnl"]) == Decimal("117.00")
    assert column - Decimal(summary["net_pnl"]) == open_rows == Decimal("-2.00")
    assert summary["open_positions"] == 2

    # А с фильтром «только закрытые» колонка сходится с шапкой до копейки.
    closed = (await client.get(POSITIONS, params={"limit": 200, "status": "closed"})).json()
    closed_column = sum((Decimal(item["net_pnl"]) for item in closed["items"]), Decimal(0))
    assert closed_column == Decimal(summary["net_pnl"])


async def test_period_is_cut_by_the_same_rule_as_the_journal(
    client: AsyncClient, account: str
) -> None:
    """Границы периода сравниваются с тем же временем события, что и в списке журнала."""
    inside = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    before = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    await seed_position(account, close_time=inside, net_pnl=Decimal("5.00"))
    await seed_position(account, close_time=before, net_pnl=Decimal("100.00"))
    # Открытая позиция попадает в период по времени открытия — как в журнале.
    await seed_open_position(account, "-1.00", open_time=inside)

    params = {"from": "2026-09-02T00:00:00Z", "to": "2026-09-03T00:00:00Z"}
    summary = (await client.get(SUMMARY, params=params)).json()
    listed = (await client.get(POSITIONS, params={**params, "limit": 200})).json()["items"]

    assert summary["trades"] == 1
    assert summary["open_positions"] == 1
    assert summary["net_pnl"] == "5.00"
    assert len(listed) == summary["trades"] + summary["open_positions"]


async def test_empty_summary_says_nothing_to_count(client: AsyncClient, account: str) -> None:
    """Ни одной сделки: суммы нулевые, средние и доли пустые."""
    payload = (await client.get(SUMMARY)).json()

    assert payload["trades"] == 0
    assert payload["net_pnl"] == "0.00"
    assert payload["winrate"] is None
    assert payload["profit_factor"] is None
    assert payload["expectancy"] is None
    assert payload["best_trade"] is None


async def test_user_without_accounts_gets_an_empty_answer(client: AsyncClient) -> None:
    """Ни одного счёта — пустой фильтр раскрывается в пустой список счетов.

    Проверяется отдельно, потому что ломается это на уровне SQL: `in ()` — не выражение,
    и пустой список параметров разворачивается особым образом.
    """
    summary = await client.get(SUMMARY)
    calendar = await client.get(CALENDAR, params={"month": "2026-09"})

    assert summary.status_code == 200, summary.text
    assert summary.json()["trades"] == 0
    assert calendar.status_code == 200, calendar.text
    assert calendar.json()["days"] == []


async def test_summary_covers_every_account_when_the_filter_is_empty(
    client: AsyncClient, account: str
) -> None:
    """Пустой фильтр — все неархивированные счета (SPEC.md 5.1), а не первый попавшийся."""
    second = await create_account(client, label="Второй")
    await seed_position(account, net_pnl=Decimal("10.00"))
    await seed_position(second, net_pnl=Decimal("25.00"))

    both = (await client.get(SUMMARY)).json()
    only_second = (await client.get(SUMMARY, params={"account_ids": second})).json()

    assert both["trades"] == 2
    assert both["net_pnl"] == "35.00"
    assert only_second["trades"] == 1
    assert only_second["net_pnl"] == "25.00"


@pytest.mark.parametrize("endpoint", [SUMMARY, CALENDAR])
async def test_foreign_account_is_not_found(
    client: AsyncClient, other_client: AsyncClient, endpoint: str
) -> None:
    """Чужой счёт неотличим от несуществующего: 404, а не пустая сводка и не 403."""
    foreign = await create_account(other_client, label="Чужой")

    response = await client.get(
        endpoint,
        params={"account_ids": foreign, "month": "2026-09"}
        if endpoint == CALENDAR
        else {"account_ids": foreign},
    )

    assert response.status_code == 404
    assert error_code(response) == "account_not_found"


# --- повторённый параметр ------------------------------------------------------

# Все маршруты, принимающие `?account_ids=`: список журнала (S2-01), сводка и календарь.
# Список ведётся здесь целиком, а не по одному тесту на домен: правило общее
# (`core/query.py`), и следующий такой маршрут обязан попасть в эту таблицу, а не завести
# четвёртую копию проверки.
ACCOUNT_SCOPED_ROUTES = [
    pytest.param(POSITIONS, {}, id="positions"),
    pytest.param(SUMMARY, {}, id="summary"),
    pytest.param(CALENDAR, {"month": "2026-09"}, id="calendar"),
]


def closed_positions_seen(endpoint: str, payload: dict[str, Any]) -> int:
    """Сколько закрытых позиций видит маршрут — одним числом для трёх разных форм ответа."""
    if endpoint == POSITIONS:
        return len(payload["items"])
    if endpoint == SUMMARY:
        return int(payload["trades"])
    return sum(int(day["trades"]) for day in payload["days"])


@pytest.mark.parametrize(("endpoint", "extra"), ACCOUNT_SCOPED_ROUTES)
async def test_repeated_account_ids_are_rejected_on_every_account_scoped_route(
    client: AsyncClient, account: str, endpoint: str, extra: dict[str, str]
) -> None:
    """`?account_ids=A&account_ids=B` — 400 на каждом маршруте, а не выборка по одному счёту.

    Так массивы сериализуют `URLSearchParams.append` и `qs` в режиме repeat, то есть
    попасть сюда клиент может без единой ошибки в своём коде. Проверка стоит зависимостью
    маршрута (`core/query.py`), и снять её можно двумя строками: без этого теста маршруты
    аналитики молча показали бы сводку и календарь по половине выбранных счетов.
    """
    second = await create_account(client, label="Второй счёт")
    await seed_position(account)
    await seed_position(second)
    tail = "".join(f"&{name}={value}" for name, value in extra.items())

    response = await client.get(f"{endpoint}?account_ids={account}&account_ids={second}{tail}")

    assert response.status_code == 400, response.text
    assert error_code(response) == "validation_error"
    assert "query.account_ids" in response.json()["error"]["details"]["fields"]

    # Оба счёта свои, и списком через запятую тот же фильтр отдаёт обе позиции: 400 выше
    # именно за повтор, а не за чужой идентификатор.
    allowed = await client.get(endpoint, params={"account_ids": f"{account},{second}", **extra})
    assert allowed.status_code == 200, allowed.text
    assert closed_positions_seen(endpoint, allowed.json()) == 2


# --- торговый день -------------------------------------------------------------

# `docs/metrics.md` §2.4: (зона, граница, момент закрытия, торговый день).
DAY_EXAMPLES = [
    ("Asia/Yekaterinburg", 0, "2026-09-01T18:30:00Z", "2026-09-01"),
    ("Asia/Yekaterinburg", 0, "2026-09-01T19:30:00Z", "2026-09-02"),
    ("Asia/Yekaterinburg", 6, "2026-09-02T00:30:00Z", "2026-09-01"),
    ("Asia/Yekaterinburg", 6, "2026-09-02T01:30:00Z", "2026-09-02"),
    ("Europe/Berlin", 0, "2026-10-25T22:30:00Z", "2026-10-25"),
    ("Europe/Berlin", 0, "2026-10-25T23:30:00Z", "2026-10-26"),
]


@pytest.mark.parametrize(("timezone", "boundary", "closed_at", "expected_day"), DAY_EXAMPLES)
async def test_position_lands_in_the_documented_day(
    client: AsyncClient,
    account: str,
    timezone: str,
    boundary: int,
    closed_at: str,
    expected_day: str,
) -> None:
    """Примеры §2.4 документа — дословно, включая ночную сделку у границы дня."""
    await set_day_rule(client, timezone, boundary)
    moment = datetime.fromisoformat(closed_at)
    await seed_position(account, close_time=moment, net_pnl=Decimal("7.00"))

    payload = (await client.get(CALENDAR, params={"month": expected_day[:7]})).json()

    assert [day["day"] for day in payload["days"]] == [expected_day]
    assert payload["timezone"] == timezone
    assert payload["day_boundary_hour"] == boundary


# `docs/metrics.md` §2.4, таблица границ: (зона, граница, день, начало, конец).
BOUNDARY_EXAMPLES = [
    ("Asia/Yekaterinburg", 0, "2026-09-02", "2026-09-01T19:00:00Z", "2026-09-02T19:00:00Z"),
    ("Asia/Yekaterinburg", 6, "2026-09-02", "2026-09-02T01:00:00Z", "2026-09-03T01:00:00Z"),
    ("Europe/Berlin", 0, "2026-03-29", "2026-03-28T23:00:00Z", "2026-03-29T22:00:00Z"),
    ("Europe/Berlin", 0, "2026-10-25", "2026-10-24T22:00:00Z", "2026-10-25T23:00:00Z"),
]


@pytest.mark.parametrize(("timezone", "boundary", "day", "starts_at", "ends_at"), BOUNDARY_EXAMPLES)
async def test_day_boundaries_match_the_document(
    client: AsyncClient,
    account: str,
    timezone: str,
    boundary: int,
    day: str,
    starts_at: str,
    ends_at: str,
) -> None:
    """Сутки перевода часов честно длятся 23 и 25 часов, а не «24 от полуночи»."""
    await set_day_rule(client, timezone, boundary)
    await seed_position(account, close_time=datetime.fromisoformat(starts_at) + timedelta(hours=1))

    payload = (await client.get(CALENDAR, params={"month": day[:7]})).json()
    found = next(item for item in payload["days"] if item["day"] == day)

    assert found["starts_at"] == starts_at
    assert found["ends_at"] == ends_at


async def test_calendar_bounds_open_the_same_day_in_the_journal(
    client: AsyncClient, account: str
) -> None:
    """Главный тест модуля: календарь и журнал не могут разойтись по дню.

    Границы дня берутся из ответа календаря и подставляются в фильтр журнала как есть.
    Это и есть переход «клик по дню → список за день» из `S2-09`.
    """
    await set_day_rule(client, "Europe/Berlin", 6)
    # Позиции по обе стороны границы 06:00 и в самой середине дня.
    for closed_at, net in (
        ("2026-09-02T03:30:00Z", "11.00"),  # 05:30 местного — ещё вчерашний день
        ("2026-09-02T05:30:00Z", "22.00"),  # 07:30 местного — уже сегодняшний
        ("2026-09-02T18:00:00Z", "33.00"),
        ("2026-09-03T03:00:00Z", "44.00"),  # 05:00 местного — всё ещё 2 сентября
    ):
        await seed_position(
            account, close_time=datetime.fromisoformat(closed_at), net_pnl=Decimal(net)
        )

    days = (await client.get(CALENDAR, params={"month": "2026-09"})).json()["days"]

    assert [day["day"] for day in days] == ["2026-09-01", "2026-09-02"]
    for day in days:
        listed = (
            await client.get(
                POSITIONS,
                params={
                    "from": day["starts_at"],
                    "to": day["ends_at"],
                    "status": "closed",
                    "limit": 200,
                },
            )
        ).json()["items"]
        column = sum((Decimal(item["net_pnl"]) for item in listed), Decimal(0))

        assert len(listed) == day["trades"], day["day"]
        assert column == Decimal(day["net_pnl"]), day["day"]


async def test_day_total_equals_the_sum_of_its_accounts(client: AsyncClient, account: str) -> None:
    """Итог дня и разбивка по счетам считаются одним запросом и обязаны сходиться."""
    second = await create_account(client, label="Второй")
    await seed_position(account, net_pnl=Decimal("10.00"))
    await seed_position(second, net_pnl=Decimal("-4.00"))
    await seed_position(second, net_pnl=Decimal("0.00"))

    day = (await client.get(CALENDAR, params={"month": "2026-09"})).json()["days"][0]

    assert day["trades"] == 3
    assert (day["wins"], day["losses"], day["breakeven"]) == (1, 1, 1)
    assert day["net_pnl"] == "6.00"
    assert sum((Decimal(item["net_pnl"]) for item in day["by_account"]), Decimal(0)) == Decimal(
        day["net_pnl"]
    )
    assert sum(item["trades"] for item in day["by_account"]) == day["trades"]
    assert {item["account_id"] for item in day["by_account"]} == {account, second}


async def test_calendar_shows_only_days_with_closed_positions(
    client: AsyncClient, account: str
) -> None:
    """Открытая позиция дня не делает: у неё нет ни результата, ни времени закрытия."""
    await seed_open_position(account, "-1.00", open_time=MOMENT)

    payload = (await client.get(CALENDAR, params={"month": "2026-09"})).json()

    assert payload["days"] == []


async def test_calendar_ignores_neighbouring_months(client: AsyncClient, account: str) -> None:
    """Месяц берётся в зоне пользователя: сделка 1 сентября по местному времени — сентябрьская."""
    await set_day_rule(client, "Asia/Yekaterinburg", 0)
    # 31 августа 19:30 UTC — это уже 1 сентября 00:30 в зоне +5.
    await seed_position(account, close_time=datetime(2026, 8, 31, 19, 30, tzinfo=UTC))
    # 30 сентября 19:30 UTC — это уже 1 октября.
    await seed_position(account, close_time=datetime(2026, 9, 30, 19, 30, tzinfo=UTC))

    days = (await client.get(CALENDAR, params={"month": "2026-09"})).json()["days"]

    assert [day["day"] for day in days] == ["2026-09-01"]


# Зоны, на которых правило дня ломается, если считать его наивно: перевод в полночь
# (`America/Santiago`), сдвиг не на целый час (`Pacific/Chatham`, `Australia/Lord_Howe`),
# обычный европейский перевод и зона без перевода вовсе.
DST_ZONES = [
    ("Europe/Berlin", date(2026, 3, 1), date(2026, 3, 31)),
    ("Europe/Berlin", date(2026, 10, 1), date(2026, 10, 31)),
    ("America/Santiago", date(2026, 9, 1), date(2026, 9, 30)),
    ("America/Santiago", date(2026, 4, 1), date(2026, 4, 30)),
    ("Pacific/Chatham", date(2026, 4, 1), date(2026, 4, 30)),
    ("Australia/Lord_Howe", date(2026, 10, 1), date(2026, 10, 31)),
    ("Asia/Yekaterinburg", date(2026, 9, 1), date(2026, 9, 30)),
]


@pytest.mark.parametrize(("timezone", "first_day", "last_day"), DST_ZONES)
@pytest.mark.parametrize("boundary", [0, 2, 3, 23])
async def test_days_cover_time_without_gaps_or_overlaps(
    live_env: pytest.MonkeyPatch,
    timezone: str,
    first_day: date,
    last_day: date,
    boundary: int,
) -> None:
    """Свойство правила дня, проверенное прямо на том SQL, который уходит в продакшен.

    Ради него день и определён интервалом: конец одного дня обязан быть началом
    следующего, иначе сделка в шов либо потеряется, либо попадёт в два дня сразу.
    """
    async with get_engine().connect() as connection:
        rows = (
            await connection.execute(
                text(f"with {DAYS_CTE} select day, starts_at, ends_at from days order by day"),
                {
                    "timezone": timezone,
                    "day_boundary_hour": boundary,
                    "first_day": first_day,
                    "last_day": last_day,
                },
            )
        ).all()

    assert [row.day for row in rows] == [
        first_day + timedelta(days=offset) for offset in range((last_day - first_day).days + 1)
    ]
    for row in rows:
        length = row.ends_at - row.starts_at
        assert timedelta(hours=22) <= length <= timedelta(hours=26), (timezone, boundary, row.day)
    for previous, following in pairwise(rows):
        assert previous.ends_at == following.starts_at, (timezone, boundary, previous.day)


# --- daily_stats ---------------------------------------------------------------


async def read_daily_stats(account_id: str) -> list[dict[str, Any]]:
    async with get_engine().connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "select day, trades, wins, losses, breakeven, gross_pnl, net_pnl, "
                    "commission, swap, fee, volume, timezone, day_boundary_hour, computed_at "
                    "from daily_stats where account_id = :account_id order by day"
                ),
                {"account_id": UUID(account_id)},
            )
        ).all()
    return [dict(row._mapping) for row in rows]


async def refresh(account_id: str, days: list[date] | None = None) -> int:
    async with get_session_factory()() as session:
        return await daily_stats.refresh(session, UUID(account_id), days)


# Денежные колонки `daily_stats`, которых нет в ответе календаря. Все — `numeric(18,2)`,
# то есть перестановка двух `sum()` в INSERT не даёт ни ошибки типа, ни красного теста:
# поймать её может только независимый пересчёт тех же строк.
CACHED_MONEY_COLUMNS = ("gross_pnl", "net_pnl", "commission", "swap", "fee")


async def test_cache_repeats_what_the_source_counts(client: AsyncClient, account: str) -> None:
    """Инвариант таблицы: строка кэша обязана совпадать с тем, что считает источник.

    Без него `daily_stats` — таблица, которую никто не читает и никто не проверяет, то
    есть заготовленное расхождение для этапа 3.

    Счётчики сверяются с календарём, деньги — со сводкой за границы того же дня: денежных
    колонок календарь не отдаёт, и без сводки четыре суммы в INSERT не сверялись бы ни с
    чем — перестановка двух из них прошла бы молча.
    """
    await set_day_rule(client, "Europe/Berlin", 6)
    await seed_worked_example(account)
    await seed_position(
        account, close_time=datetime(2026, 9, 5, 10, 0, tzinfo=UTC), net_pnl=Decimal("13.00")
    )

    written = await refresh(account)
    days = (await client.get(CALENDAR, params={"month": "2026-09"})).json()["days"]
    cached = await read_daily_stats(account)

    assert written == len(days) == len(cached) == 2
    for expected, row in zip(days, cached, strict=True):
        assert str(row["day"]) == expected["day"]
        assert row["trades"] == expected["trades"]
        assert row["wins"] == expected["wins"]
        assert row["losses"] == expected["losses"]
        assert row["breakeven"] == expected["breakeven"]
        assert row["net_pnl"] == Decimal(expected["net_pnl"])

        summary = await client.get(
            SUMMARY,
            params={
                "account_ids": account,
                "from": expected["starts_at"],
                "to": expected["ends_at"],
            },
        )
        assert summary.status_code == 200, summary.text
        totals = summary.json()
        assert totals["trades"] == expected["trades"], expected["day"]
        for column in CACHED_MONEY_COLUMNS:
            assert row[column] == Decimal(totals[column]), (expected["day"], column)


async def test_cache_records_the_rule_it_was_computed_with(
    client: AsyncClient, account: str
) -> None:
    """День зависит от настроек пользователя: без них строка неотличима от протухшей."""
    await set_day_rule(client, "Europe/Berlin", 6)
    await seed_position(account)

    await refresh(account)
    row = (await read_daily_stats(account))[0]

    assert row["timezone"] == "Europe/Berlin"
    assert row["day_boundary_hour"] == 6
    assert row["computed_at"] is not None
    assert row["volume"] == Decimal("0.10000000")


async def test_refresh_is_idempotent(client: AsyncClient, account: str) -> None:
    """Повторный прогон даёт то же самое: задача сносит дни и собирает их заново."""
    await seed_worked_example(account)

    first_written = await refresh(account)
    first = await read_daily_stats(account)
    second_written = await refresh(account)
    second = await read_daily_stats(account)

    assert first_written == second_written == 1
    assert [row["trades"] for row in first] == [row["trades"] for row in second]
    assert [row["net_pnl"] for row in first] == [row["net_pnl"] for row in second]


async def test_refresh_touches_only_the_requested_days(client: AsyncClient, account: str) -> None:
    """Список дней — оптимизация: соседние дни задача не трогает."""
    await seed_position(account, close_time=datetime(2026, 9, 2, 10, 0, tzinfo=UTC))
    await seed_position(account, close_time=datetime(2026, 9, 3, 10, 0, tzinfo=UTC))

    await refresh(account)
    await execute(
        "update daily_stats set trades = 99 where account_id = :account_id and day = :day",
        account_id=UUID(account),
        day=date(2026, 9, 3),
    )
    await refresh(account, [date(2026, 9, 2)])

    rows = {str(row["day"]): row["trades"] for row in await read_daily_stats(account)}
    assert rows == {"2026-09-02": 1, "2026-09-03": 99}


async def test_refresh_forgets_days_that_lost_their_positions(
    client: AsyncClient, account: str
) -> None:
    """Пересборка позиций может унести день целиком — строка кэша обязана исчезнуть."""
    await seed_position(account)
    await refresh(account)
    assert await read_daily_stats(account)

    await execute("delete from positions where account_id = :account_id", account_id=UUID(account))
    written = await refresh(account)

    assert written == 0
    assert await read_daily_stats(account) == []


async def test_refresh_of_a_missing_account_is_not_an_error() -> None:
    """Задача могла встать в очередь до удаления счёта; падать на этом ей незачем."""
    assert await refresh(str(uuid4())) == 0


async def test_deleting_the_account_removes_its_cache(client: AsyncClient, account: str) -> None:
    """Единственный каскад на производных данных: кэш удалённого счёта бессмыслен."""
    await seed_position(account)
    await refresh(account)
    assert await read_daily_stats(account)

    response = await client.delete(f"{ACCOUNTS}/{account}")

    assert response.status_code == 204, response.text
    assert await read_daily_stats(account) == []
