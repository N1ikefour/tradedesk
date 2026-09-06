"""Журнал против настоящих Postgres и Redis — DoD S2-01.

Главный тест здесь один: `test_pages_cover_every_row_once_on_identical_sort_values`.
Все пять полей сортировки SPEC.md 5.4 неуникальны, поэтому позиции сеются с **дословно
одинаковыми** значениями во всех пяти сразу, и страницы обходятся от первой до последней.
Тест на разных значениях был бы зелёным при любой реализации курсора и не доказывал бы
ничего: расходятся `ORDER BY` и предикат курсора ровно там, где значения совпадают.

`positions` до `S1-03` не наполняет никто, поэтому строки вставляются напрямую. Форма
строки взята из `SPEC.md` 3.3 и миграции `b07a46275bbc`, а не из сборщика позиций — его
ещё нет, и подстраиваться под него будет уже он сам.

Идентификаторы позиций — `uuid4`, а не `uuid7`: uuid7 возрастает вместе со временем
вставки, порядок по `id` совпадает с порядком вставки, и ошибка порядка прячется за этим
совпадением. Насколько — измерено на двух мутациях `service.py`: снять `positions.id`
из `_order_by` и снять его же из предиката `_after`. Мутацию `_order_by` uuid4 убивает во
всех 12 параметризациях ниже, uuid7 — в 8 из 12; мутацию `_after` обе убивают в 12 из 12.
То есть ложно зелёным uuid7 тест не сделал бы, но слабее делает.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import event, text
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from alembic import command
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.redis import get_redis
from app.domains.journal.cursor import SORT_DIRECTIONS, SORT_FIELDS

pytestmark = pytest.mark.integration

API = "/api/v1"
API_DIR = Path(__file__).resolve().parents[2]

ORIGIN = "http://test"
CLIENT_IP = "203.0.113.11"
EMAIL = "journal@example.test"
OTHER_EMAIL = "stranger@example.test"

ACCOUNTS = f"{API}/accounts"
POSITIONS = f"{API}/journal/positions"

# Значение, которого нет больше нигде: по нему тело ответа обыскивается на утечку.
INVESTOR_PASSWORD = "s3cret-investor-pw-4b71de"

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

# Одна точка отсчёта на весь модуль: все «одинаковые» значения одинаковы дословно.
MOMENT = datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC)

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
    """Миграции — один раз на модуль; между тестами чистятся только данные.

    `get_settings.cache_clear()` вокруг обеих команд обязателен по той же причине, что
    и в `test_accounts.py`: `alembic/env.py` берёт URL из закэшированных настроек, а
    сбрасывает кэш функциональная фикстура — то есть не в setup и teardown модуля.
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


async def execute(statement: str, **params: Any) -> None:
    async with get_engine().begin() as connection:
        await connection.execute(text(statement), params)


async def create_account(client: AsyncClient, **overrides: Any) -> str:
    response = await client.post(ACCOUNTS, json={**MT5_BODY, **overrides})
    assert response.status_code == 201, response.text
    account_id = response.json()["id"]
    assert isinstance(account_id, str)
    return account_id


@pytest.fixture
async def account(client: AsyncClient) -> str:
    return await create_account(client)


def error_code(response: Response) -> str:
    code = response.json()["error"]["code"]
    assert isinstance(code, str)
    return code


_next_broker_id = iter(range(1000, 100000))


async def seed_position(account_id: str, **overrides: Any) -> UUID:
    """Одна закрытая позиция со значениями по умолчанию; отличается только тем, что задано."""
    identifier = overrides.pop("id", None) or uuid4()
    row: dict[str, Any] = {
        "id": identifier,
        "account_id": UUID(account_id),
        "position_id": next(_next_broker_id),
        "symbol_raw": "EURUSD.m",
        "symbol_norm": "EURUSD",
        "direction": "long",
        "status": "closed",
        "open_time": MOMENT - timedelta(hours=1),
        "close_time": MOMENT,
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


async def seed_open_position(account_id: str, **overrides: Any) -> UUID:
    """Открытая позиция: ни времени закрытия, ни длительности, ни цены выхода."""
    return await seed_position(
        account_id,
        status="open",
        close_time=None,
        duration_seconds=None,
        avg_exit_price=None,
        volume_closed=Decimal("0"),
        close_reason=None,
        **overrides,
    )


async def seed_entry(
    position_id: UUID, notes: str | None = None, tags: list[str] | None = None
) -> None:
    await execute(
        "insert into journal_entries (position_id, notes, tags, updated_at) "
        "values (:id, :notes, :tags, :moment)",
        id=position_id,
        notes=notes,
        tags=tags or [],
        moment=MOMENT,
    )


async def seed_reflection(position_id: UUID, *, filled: bool) -> None:
    await execute(
        "insert into reflections (position_id, setup_grade, mistakes, filled_at, updated_at) "
        "values (:id, 'B', :mistakes, :filled_at, :moment)",
        id=position_id,
        mistakes=["early_entry"],
        filled_at=MOMENT if filled else None,
        moment=MOMENT,
    )


async def seed_attachment(position_id: UUID) -> None:
    await execute(
        "insert into attachments (id, position_id, s3_key, content_type, created_at) "
        "values (:id, :position, 'k', 'image/png', :moment)",
        id=uuid4(),
        position=position_id,
        moment=MOMENT,
    )


async def seed_deal(account_id: str, broker_position_id: int, ticket: int, entry: str) -> None:
    await execute(
        """
        insert into deals (
            account_id, deal_ticket, position_id, symbol_raw, deal_type, entry,
            volume, price, profit, commission, swap, fee, time_utc, time_server,
            comment, magic, raw, source
        ) values (
            :account, :ticket, :position, 'EURUSD.m', 'buy', :entry,
            0.1, 1.08543, 10.00, -0.35, 0, 0, :moment, :server_moment,
            :comment, 42, :raw, 'collector'
        )
        """,
        account=UUID(account_id),
        ticket=ticket,
        position=broker_position_id,
        entry=entry,
        moment=MOMENT,
        server_moment=MOMENT + timedelta(hours=3),
        comment="tp\nhit",
        raw='{"secret_from_terminal": "не для клиента"}',
    )


async def broker_id_of(position_id: UUID) -> int:
    async with get_engine().connect() as connection:
        value = (
            await connection.execute(
                text("select position_id from positions where id = :id"), {"id": position_id}
            )
        ).scalar_one()
    assert isinstance(value, int)
    return value


async def page(client: AsyncClient, **params: Any) -> tuple[list[dict[str, Any]], str | None]:
    response = await client.get(POSITIONS, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    items = body["items"]
    assert isinstance(items, list)
    cursor = body["next_cursor"]
    assert cursor is None or isinstance(cursor, str)
    return items, cursor


async def walk(client: AsyncClient, *, expected: int, **params: Any) -> list[str]:
    """Все страницы подряд по `next_cursor`. Возвращает id в том порядке, в каком выданы.

    Предохранитель от бесконечного цикла стоит намеренно: курсор, который не двигается,
    иначе повесил бы прогон вместо того, чтобы упасть.
    """
    collected: list[str] = []
    cursor: str | None = None
    for _ in range(expected * 2 + 5):
        items, cursor = await page(client, **params, **({"cursor": cursor} if cursor else {}))
        collected.extend(str(item["id"]) for item in items)
        if cursor is None:
            return collected
    raise AssertionError(f"курсор не кончился за {expected * 2 + 5} страниц: {collected}")


# --- курсор по неуникальному ключу: главное доказательство ---------------------


@pytest.mark.parametrize("field", SORT_FIELDS)
@pytest.mark.parametrize("direction", SORT_DIRECTIONS)
async def test_pages_cover_every_row_once_on_identical_sort_values(
    client: AsyncClient, account: str, field: str, direction: str
) -> None:
    """Страницы отдают каждую позицию ровно один раз, когда ключ сортировки не различает.

    Все семь позиций совпадают дословно во **всех** пяти полях сортировки сразу, поэтому
    единственное, чем они отличаются, — `positions.id`. Курсор, хранящий только значение
    поля, здесь либо зациклится, либо перепрыгнет через страницу.
    """
    seeded = {str(await seed_position(account)) for _ in range(7)}

    collected = await walk(client, expected=len(seeded), limit=2, sort=f"{field}:{direction}")

    assert len(collected) == len(seeded), f"повторы или пропуски: {collected}"
    assert set(collected) == seeded


@pytest.mark.parametrize("direction", SORT_DIRECTIONS)
async def test_pages_cover_open_positions_with_no_sort_value(
    client: AsyncClient, account: str, direction: str
) -> None:
    """Группа без значения ключа обходится так же полно, как и остальные.

    У открытых позиций `close_time` пуст, и курсор обязан уметь указывать **внутрь**
    этой группы: иначе вторая страница либо начнёт список заново, либо перескочит через
    весь остаток открытых.
    """
    opened = {str(await seed_open_position(account)) for _ in range(5)}
    closed = {str(await seed_position(account)) for _ in range(5)}

    collected = await walk(client, expected=10, limit=2, sort=f"close_time:{direction}")

    assert len(collected) == 10, f"повторы или пропуски: {collected}"
    assert set(collected) == opened | closed
    # Открытые идут первой группой в обе стороны — правило 3 `service.py`.
    assert set(collected[:5]) == opened


async def test_tail_is_reachable_when_the_sort_value_is_long(
    client: AsyncClient, account: str
) -> None:
    """Курсор, который выдал API, обязан быть принят API — при любой длине значения ключа.

    Предел на длине значения ключа этого не давал: `next_cursor` с символом длиннее предела
    возвращался клиенту и на следующем же запросе получал `400`, то есть хвост списка был
    недостижим. `positions.symbol_norm` — `text`; такие символы придут с ручными сделками
    (`S2-03`) и входом CSV (SPEC.md 5.3), где символ печатает человек.
    """
    long_symbol = "X" * 80
    seeded = {
        str(await seed_position(account, symbol_norm=long_symbol, symbol_raw=long_symbol))
        for _ in range(3)
    }

    collected = await walk(client, expected=3, limit=1, sort="symbol_norm:asc")

    assert set(collected) == seeded


async def test_last_page_has_no_cursor(client: AsyncClient, account: str) -> None:
    await seed_position(account)
    await seed_position(account)

    items, cursor = await page(client, limit=2)

    assert len(items) == 2
    assert cursor is None, "на последней странице курсор обещает несуществующую следующую"


async def test_empty_journal_returns_empty_page(client: AsyncClient, account: str) -> None:
    items, cursor = await page(client)

    assert items == []
    assert cursor is None


async def test_cursor_survives_a_changed_filter(client: AsyncClient, account: str) -> None:
    """Курсор не несёт фильтров: со сменой фильтра он остаётся годной точкой ключа."""
    for _ in range(3):
        await seed_position(account, symbol_norm="EURUSD")
    gold = await seed_position(account, symbol_norm="XAUUSD")

    _, cursor = await page(client, limit=1, sort="symbol_norm:asc")
    assert cursor is not None
    items, _ = await page(client, limit=10, sort="symbol_norm:asc", cursor=cursor, symbol="XAUUSD")

    assert [item["id"] for item in items] == [str(gold)]


# --- курсор: порча и рассогласование ------------------------------------------


@pytest.mark.parametrize("broken", ["не-курсор", "", "!!!", "eyJzIjoiY2xvc2VfdGltZSJ9"])
async def test_broken_cursor_is_a_validation_error(
    client: AsyncClient, account: str, broken: str
) -> None:
    """Испорченный курсор — ошибка параметра запроса, а не доменный код (SPEC.md 5.1)."""
    response = await client.get(POSITIONS, params={"cursor": broken})

    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "query.cursor" in error["details"]["fields"]


async def test_cursor_from_another_sort_is_rejected(client: AsyncClient, account: str) -> None:
    """Курсор помнит порядок, под который собран: под другим он означал бы другую строку."""
    for _ in range(3):
        await seed_position(account)
    _, cursor = await page(client, limit=1, sort="close_time:desc")
    assert cursor is not None

    response = await client.get(POSITIONS, params={"cursor": cursor, "sort": "net_pnl:asc"})

    assert response.status_code == 400
    assert "query.cursor" in response.json()["error"]["details"]["fields"]


async def test_unknown_sort_is_rejected(client: AsyncClient, account: str) -> None:
    response = await client.get(POSITIONS, params={"sort": "account_id:desc"})

    assert response.status_code == 400
    assert "query.sort" in response.json()["error"]["details"]["fields"]


async def test_unknown_query_parameter_is_rejected(client: AsyncClient, account: str) -> None:
    """Опечатка в имени фильтра иначе молча вернула бы нефильтрованный список."""
    response = await client.get(POSITIONS, params={"symbols": "EURUSD"})

    assert response.status_code == 400
    assert "query.symbols" in response.json()["error"]["details"]["fields"]


# --- скоупинг по владельцу ----------------------------------------------------


async def test_foreign_account_in_filter_is_404(
    client: AsyncClient, other_client: AsyncClient, account: str
) -> None:
    """Чужой счёт неотличим от несуществующего: 404, а не 403 и не пустой список."""
    foreign = await create_account(other_client, login=7009999)

    response = await client.get(POSITIONS, params={"account_ids": foreign})

    assert response.status_code == 404
    assert error_code(response) == "account_not_found"
    assert response.json()["error"]["details"]["account_ids"] == [foreign]


async def test_mixed_account_ids_fail_whole_request(
    client: AsyncClient, other_client: AsyncClient, account: str
) -> None:
    """Свой и чужой вперемешку — 404 на весь запрос.

    Отдать «своё из списка» значило бы вернуть не тот список, о котором просили: человек
    считал бы неполную выборку полной и не узнал бы об этом никогда.
    """
    await seed_position(account)
    foreign = await create_account(other_client, login=7008888)

    response = await client.get(POSITIONS, params={"account_ids": f"{account},{foreign}"})

    assert response.status_code == 404
    assert response.json()["error"]["details"]["account_ids"] == [foreign]


async def test_unknown_account_id_is_404(client: AsyncClient, account: str) -> None:
    response = await client.get(POSITIONS, params={"account_ids": str(uuid4())})

    assert response.status_code == 404
    assert error_code(response) == "account_not_found"


async def test_foreign_position_card_is_404(client: AsyncClient, other_client: AsyncClient) -> None:
    foreign_account = await create_account(other_client, login=7007777)
    foreign_position = await seed_position(foreign_account)

    response = await client.get(f"{POSITIONS}/{foreign_position}")

    assert response.status_code == 404
    assert error_code(response) == "position_not_found"


async def test_missing_position_card_is_404(client: AsyncClient, account: str) -> None:
    response = await client.get(f"{POSITIONS}/{uuid4()}")

    assert response.status_code == 404
    assert error_code(response) == "position_not_found"


async def test_foreign_positions_never_appear_in_the_default_scope(
    client: AsyncClient, other_client: AsyncClient, account: str
) -> None:
    """Пустой фильтр — все счета **пользователя**, а не все счета в базе."""
    foreign_account = await create_account(other_client, login=7006666)
    await seed_position(foreign_account)
    mine = await seed_position(account)

    items, _ = await page(client)

    assert [item["id"] for item in items] == [str(mine)]


async def test_archived_account_is_hidden_by_default_and_visible_on_request(
    client: AsyncClient, account: str
) -> None:
    """Архив уходит из списка по умолчанию, но сделки остаются (SPEC.md 5.2)."""
    archived_account = await create_account(client, login=7005555)
    archived_position = await seed_position(archived_account)
    live_position = await seed_position(account)
    assert (await client.post(f"{ACCOUNTS}/{archived_account}/archive")).status_code == 200

    default_items, _ = await page(client)
    explicit_items, _ = await page(client, account_ids=archived_account)

    assert [item["id"] for item in default_items] == [str(live_position)]
    assert [item["id"] for item in explicit_items] == [str(archived_position)]


async def test_card_of_an_archived_account_still_opens(client: AsyncClient) -> None:
    """Ссылка на карточку обязана открыться и после архивации счёта."""
    archived_account = await create_account(client, login=7004444)
    position = await seed_position(archived_account)
    assert (await client.post(f"{ACCOUNTS}/{archived_account}/archive")).status_code == 200

    response = await client.get(f"{POSITIONS}/{position}")

    assert response.status_code == 200


# --- фильтры ------------------------------------------------------------------


async def test_status_filter(client: AsyncClient, account: str) -> None:
    closed = await seed_position(account)
    opened = await seed_open_position(account)

    closed_items, _ = await page(client, status="closed")
    open_items, _ = await page(client, status="open")

    assert [item["id"] for item in closed_items] == [str(closed)]
    assert [item["id"] for item in open_items] == [str(opened)]


async def test_period_filter_uses_close_time_and_falls_back_to_open_time(
    client: AsyncClient, account: str
) -> None:
    """Открытая позиция сравнивается по времени открытия — иначе фильтр по датам прячет её.

    У открытых `close_time` пуст, и любое сравнение с ним ложно: без `coalesce` фильтр
    периода выбросил бы из журнала все позиции, которые человек держит прямо сейчас.
    """
    inside = await seed_position(account, close_time=MOMENT)
    before = await seed_position(account, close_time=MOMENT - timedelta(days=10))
    opened_inside = await seed_open_position(account, open_time=MOMENT)

    items, _ = await page(
        client,
        **{
            "from": (MOMENT - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
            "to": (MOMENT + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
    )

    found = {item["id"] for item in items}
    assert found == {str(inside), str(opened_inside)}
    assert str(before) not in found


async def test_period_right_edge_is_exclusive(client: AsyncClient, account: str) -> None:
    """Полуинтервал: `to` не включает свою границу."""
    edge = await seed_position(account, close_time=MOMENT)

    items, _ = await page(client, **{"to": MOMENT.isoformat().replace("+00:00", "Z")})
    inclusive, _ = await page(
        client, **{"to": (MOMENT + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")}
    )

    assert items == []
    assert [item["id"] for item in inclusive] == [str(edge)]


async def test_naive_period_boundary_is_rejected(client: AsyncClient, account: str) -> None:
    """Время без зоны — незаданный вопрос, а не UTC по умолчанию."""
    response = await client.get(POSITIONS, params={"from": "2026-09-01T00:00:00"})

    assert response.status_code == 400
    assert "query.from" in response.json()["error"]["details"]["fields"]


async def test_reversed_period_is_rejected(client: AsyncClient, account: str) -> None:
    """`from > to` — ошибка, а не пустой журнал: пустой список читается как «сделок нет»."""
    response = await client.get(
        POSITIONS, params={"from": "2026-09-02T00:00:00Z", "to": "2026-09-01T00:00:00Z"}
    )

    assert response.status_code == 400


async def test_symbol_filter_is_exact_and_case_insensitive(
    client: AsyncClient, account: str
) -> None:
    gold = await seed_position(account, symbol_raw="XAUUSD.m", symbol_norm="XAUUSD")
    await seed_position(account, symbol_norm="EURUSD")

    items, _ = await page(client, symbol="xauusd")

    assert [item["id"] for item in items] == [str(gold)]


async def test_direction_filter(client: AsyncClient, account: str) -> None:
    short = await seed_position(account, direction="short")
    await seed_position(account, direction="long")

    items, _ = await page(client, direction="short")

    assert [item["id"] for item in items] == [str(short)]


async def test_result_filter_and_field_follow_the_spec(client: AsyncClient, account: str) -> None:
    """SPEC.md 5.4 дословно: `> 0` win, `< 0` loss, `= 0` breakeven — и только у закрытых.

    Точный ноль, без полосы вокруг него. Цена решения честная: комиссия сдвигает `net_pnl`
    с нуля почти всегда, поэтому `be` на реальном счёте будет почти пустым.
    """
    win = await seed_position(account, net_pnl=Decimal("0.01"))
    loss = await seed_position(account, net_pnl=Decimal("-0.01"))
    breakeven = await seed_position(account, net_pnl=Decimal("0.00"))
    running = await seed_open_position(account, net_pnl=Decimal("-0.35"))

    by_result = {
        name: {item["id"] for item in (await page(client, result=name))[0]}
        for name in ("win", "loss", "be")
    }
    everything, _ = await page(client)
    result_of = {item["id"]: item["result"] for item in everything}

    assert by_result == {"win": {str(win)}, "loss": {str(loss)}, "be": {str(breakeven)}}
    assert result_of[str(win)] == "win"
    assert result_of[str(loss)] == "loss"
    assert result_of[str(breakeven)] == "be"
    # У открытой позиции итога ещё нет: комиссия входа сделала бы её «убыточной» ни за что.
    assert result_of[str(running)] is None


async def test_tags_filter_narrows_with_each_tag(client: AsyncClient, account: str) -> None:
    """`tags=a,b` — позиция должна нести **оба**: второй тег сужает выборку, а не расширяет."""
    both = await seed_position(account)
    one = await seed_position(account)
    await seed_position(account)
    await seed_entry(both, tags=["news", "breakout"])
    await seed_entry(one, tags=["news"])

    news, _ = await page(client, tags="news")
    both_tags, _ = await page(client, tags="news,breakout")

    assert {item["id"] for item in news} == {str(both), str(one)}
    assert [item["id"] for item in both_tags] == [str(both)]


async def test_has_reflection_filter(client: AsyncClient, account: str) -> None:
    """`filled_at`, а не наличие строки: пустая рефлексия — это «не заполнена»."""
    filled = await seed_position(account)
    started = await seed_position(account)
    absent = await seed_position(account)
    await seed_reflection(filled, filled=True)
    await seed_reflection(started, filled=False)

    yes, _ = await page(client, has_reflection="true")
    no, _ = await page(client, has_reflection="false")

    assert [item["id"] for item in yes] == [str(filled)]
    assert {item["id"] for item in no} == {str(started), str(absent)}


async def test_search_covers_symbol_and_notes(client: AsyncClient, account: str) -> None:
    """`q` ищет по символу (обоим написаниям) и по тексту заметки — и больше нигде."""
    by_norm = await seed_position(account, symbol_raw="XAUUSD.m", symbol_norm="XAUUSD")
    by_raw = await seed_position(account, symbol_raw="EURUSD.pro", symbol_norm="EURUSD")
    by_notes = await seed_position(account, symbol_norm="GBPJPY", symbol_raw="GBPJPY")
    await seed_entry(by_notes, notes="Вход по пробою уровня")
    only_tag = await seed_position(account, symbol_norm="USDCHF", symbol_raw="USDCHF")
    await seed_entry(only_tag, tags=["пробой"])

    gold, _ = await page(client, q="xau")
    pro, _ = await page(client, q=".pro")
    notes, _ = await page(client, q="пробою")

    assert [item["id"] for item in gold] == [str(by_norm)]
    assert [item["id"] for item in pro] == [str(by_raw)]
    # Тег в выдачу не попадает: у тегов есть точный фильтр, и подстрока ломала бы его смысл.
    assert [item["id"] for item in notes] == [str(by_notes)]


async def test_search_wildcards_are_escaped(client: AsyncClient, account: str) -> None:
    """`%` от пользователя — символ, а не шаблон: иначе поиск означал бы «показать всё»."""
    await seed_position(account, symbol_norm="EURUSD", symbol_raw="EURUSD")

    items, _ = await page(client, q="%")

    assert items == []


async def test_search_underscore_is_a_character_not_a_wildcard(
    client: AsyncClient, account: str
) -> None:
    """`_` в LIKE — «любой один символ», то есть незаэкранированный он находит вообще всё.

    Отдельно от `%`: снять из списка подстановок одно только подчёркивание — правка в один
    символ, а видна она лишь на запросе, который его содержит.
    """
    underscored = await seed_position(account, symbol_norm="EUR_USD", symbol_raw="EUR_USD")
    await seed_position(account, symbol_norm="EURUSD", symbol_raw="EURUSD")

    items, _ = await page(client, q="_")

    assert [item["id"] for item in items] == [str(underscored)]


async def test_search_backslash_is_a_character_not_an_escape(
    client: AsyncClient, account: str
) -> None:
    """Сам символ экранирования тоже экранируется — иначе он съедает следующую букву.

    Без удвоения `\\` в `%C:\\trade%` Postgres читает `\\t` как «буква t», шаблон
    превращается в `%C:trade%`, и поиск находит не ту строку. В заметках путь к скриншоту
    или к логу терминала — ровно тот текст, который человек ищет.
    """
    windows_path = await seed_position(account, symbol_norm="GBPJPY", symbol_raw="GBPJPY")
    await seed_entry(windows_path, notes="скрин в C:\\trade\\log")
    decoy = await seed_position(account, symbol_norm="AUDUSD", symbol_raw="AUDUSD")
    await seed_entry(decoy, notes="скрин в C:trade")

    items, _ = await page(client, q="C:\\trade")

    assert [item["id"] for item in items] == [str(windows_path)]


# --- повторённый параметр -----------------------------------------------------


async def test_repeated_account_ids_do_not_silently_narrow_the_page(
    client: AsyncClient, account: str
) -> None:
    """`?account_ids=A&account_ids=B` — 400, а не `200` с выборкой по одному счёту из двух.

    Так массивы сериализуют `URLSearchParams.append` и `qs` в режиме repeat, то есть
    попасть сюда клиент может без единой ошибки в своём коде. Молча вернуть строки только
    последнего счёта значит показать половину журнала как целый.
    """
    second = await create_account(client, label="Второй счёт", login=7003333)
    mine = await seed_position(account)
    other = await seed_position(second)

    response = await client.get(f"{POSITIONS}?account_ids={account}&account_ids={second}")

    assert response.status_code == 400, response.text
    assert error_code(response) == "validation_error"
    assert "query.account_ids" in response.json()["error"]["details"]["fields"]
    # Оба счёта — свои: 400 здесь именно за повтор, а не за чужой идентификатор.
    both, _ = await page(client, account_ids=f"{account},{second}")
    assert {item["id"] for item in both} == {str(mine), str(other)}


@pytest.mark.parametrize(
    "query",
    [
        pytest.param("status=open&status=closed", id="status"),
        pytest.param("symbol=EURUSD&symbol=XAUUSD", id="symbol"),
        pytest.param("limit=1&limit=50", id="limit"),
        pytest.param("q=один&q=два", id="q"),
        pytest.param("sort=net_pnl:asc&sort=close_time:desc", id="sort"),
    ],
)
async def test_repeated_scalar_filter_is_rejected(
    client: AsyncClient, account: str, query: str
) -> None:
    """Повтор ломает любой скалярный фильтр одинаково: побеждает последний, первый исчезает."""
    response = await client.get(f"{POSITIONS}?{query}")

    assert response.status_code == 400, response.text
    assert error_code(response) == "validation_error"
    name = query.split("=", 1)[0]
    assert f"query.{name}" in response.json()["error"]["details"]["fields"]


async def test_every_repeated_parameter_is_named_at_once(client: AsyncClient, account: str) -> None:
    """Клиент, который сериализует массивы повтором, прислал так все свои фильтры сразу."""
    response = await client.get(f"{POSITIONS}?tags=a&tags=b&status=open&status=closed")

    assert response.status_code == 400, response.text
    assert set(response.json()["error"]["details"]["fields"]) == {"query.tags", "query.status"}


async def test_a_single_parameter_is_not_mistaken_for_a_repeat(
    client: AsyncClient, account: str
) -> None:
    """Границу видно только с обеих сторон: одиночные параметры проходят как раньше."""
    target = await seed_position(account, symbol_norm="XAUUSD", symbol_raw="XAUUSD")

    items, _ = await page(client, symbol="XAUUSD", status="closed", limit=10)

    assert [item["id"] for item in items] == [str(target)]


async def test_filters_combine(client: AsyncClient, account: str) -> None:
    """Несколько фильтров разом сужают выборку, а не спорят друг с другом."""
    target = await seed_position(
        account, symbol_norm="XAUUSD", symbol_raw="XAUUSD", direction="short", net_pnl=Decimal("5")
    )
    await seed_entry(target, notes="план сработал", tags=["news"])
    await seed_reflection(target, filled=True)
    await seed_position(account, symbol_norm="XAUUSD", symbol_raw="XAUUSD", direction="long")
    other = await seed_position(
        account, symbol_norm="XAUUSD", symbol_raw="XAUUSD", direction="short"
    )
    await seed_entry(other, tags=["news"])

    items, _ = await page(
        client,
        symbol="XAUUSD",
        direction="short",
        status="closed",
        result="win",
        tags="news",
        has_reflection="true",
        q="план",
        **{"from": (MOMENT - timedelta(days=1)).isoformat().replace("+00:00", "Z")},
    )

    assert [item["id"] for item in items] == [str(target)]


async def test_limit_bounds_are_enforced(client: AsyncClient, account: str) -> None:
    for value in ("0", "201", "не-число"):
        response = await client.get(POSITIONS, params={"limit": value})
        assert response.status_code == 400, value
        assert "query.limit" in response.json()["error"]["details"]["fields"]


# --- форма ответа --------------------------------------------------------------


async def test_list_item_shape(client: AsyncClient, account: str) -> None:
    position = await seed_position(account)
    await seed_entry(position, notes="  первая   строка  \n  вторая  ", tags=["news"])
    await seed_reflection(position, filled=True)
    await seed_attachment(position)

    items, _ = await page(client)

    item = items[0]
    assert item["id"] == str(position)
    assert item["account"] == {
        "id": account,
        "label": MT5_BODY["label"],
        "color": item["account"]["color"],
        "is_demo": True,
    }
    assert item["journal_entry"] == {
        "tags": ["news"],
        "has_notes": True,
        "notes_preview": "первая строка вторая",
        "risk_amount": None,
        "updated_at": "2026-09-01T12:00:00Z",
    }
    assert item["reflection"] == {"filled_at": "2026-09-01T12:00:00Z"}
    assert item["attachments_count"] == 1


async def test_list_item_without_user_layer(client: AsyncClient, account: str) -> None:
    await seed_position(account)

    items, _ = await page(client)

    assert items[0]["journal_entry"] is None
    assert items[0]["reflection"] is None
    assert items[0]["attachments_count"] == 0


async def test_money_and_quantities_are_strings(client: AsyncClient, account: str) -> None:
    """В JSON нет десятичного типа: числом `10.50` уехало бы double и потеряло масштаб."""
    await seed_position(account, net_pnl=Decimal("10.50"), volume_opened=Decimal("0.10"))

    items, _ = await page(client)

    item = items[0]
    assert item["net_pnl"] == "10.50"
    assert item["volume_opened"] == "0.10000000"
    assert item["gross_pnl"] == "10.35"


async def test_times_are_iso_with_z(client: AsyncClient, account: str) -> None:
    await seed_position(account)

    items, _ = await page(client)

    item = items[0]
    assert item["close_time"] == "2026-09-01T12:00:00Z"
    assert item["open_time"] == "2026-09-01T11:00:00Z"
    assert item["rebuilt_at"] == "2026-09-01T12:00:00Z"


async def test_card_carries_deals_entry_and_reflection(client: AsyncClient, account: str) -> None:
    position = await seed_position(account)
    broker_id = await broker_id_of(position)
    await seed_deal(account, broker_id, ticket=2, entry="out")
    await seed_deal(account, broker_id, ticket=1, entry="in")
    await seed_entry(position, notes="полный текст", tags=["news"])
    await seed_reflection(position, filled=True)

    response = await client.get(f"{POSITIONS}/{position}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(position)
    assert [deal["deal_ticket"] for deal in body["deals"]] == [1, 2]
    assert body["journal_entry"]["notes"] == "полный текст"
    assert body["reflection"]["setup_grade"] == "B"
    assert body["reflection"]["mistakes"] == ["early_entry"]
    assert body["attachments_count"] == 0


async def test_card_deal_hides_raw_and_server_time(client: AsyncClient, account: str) -> None:
    """`raw` — полный ответ терминала, `time_server` — отладка (SPEC.md 3.3). Наружу не идут."""
    position = await seed_position(account)
    await seed_deal(account, await broker_id_of(position), ticket=1, entry="in")

    response = await client.get(f"{POSITIONS}/{position}")

    body = response.json()
    deal = body["deals"][0]
    assert "raw" not in deal
    assert "time_server" not in deal
    assert "не для клиента" not in response.text
    # Комментарий терминала показывается, но одной строкой и через тот же санитайзер (X-21).
    assert deal["comment"] == "tp hit"


async def test_no_response_carries_the_account_password(client: AsyncClient, account: str) -> None:
    """Пароль счёта не покидает `/internal/collector/assignments` (CLAUDE.md §5)."""
    position = await seed_position(account)
    await seed_deal(account, await broker_id_of(position), ticket=1, entry="in")

    listing = await client.get(POSITIONS)
    card = await client.get(f"{POSITIONS}/{position}")

    assert INVESTOR_PASSWORD not in listing.text
    assert INVESTOR_PASSWORD not in card.text


# --- вложения считаются одним запросом ----------------------------------------


async def test_attachments_count_does_not_grow_the_query_count(
    client: AsyncClient, account: str
) -> None:
    """Счётчик вложений — один запрос на страницу, а не по запросу на строку.

    Таблица пуста до `S2-04`, и разницу сегодня не видно. Заметной она станет ровно тогда,
    когда вложения появятся, а переписывать список к тому моменту будет уже некому: счётчик
    по строке на этом экране — N+1 на каждый скролл.
    """
    statements: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        statements.append(statement)

    first = await seed_position(account)
    await seed_attachment(first)
    event.listen(get_engine().sync_engine, "before_cursor_execute", record)
    try:
        await page(client)
        one_row = len(statements)
        for _ in range(9):
            position = await seed_position(account)
            await seed_attachment(position)
        statements.clear()
        await page(client)
        ten_rows = len(statements)
    finally:
        event.remove(get_engine().sync_engine, "before_cursor_execute", record)

    assert ten_rows == one_row, f"запросов на страницу стало больше: {one_row} -> {ten_rows}"
    items, _ = await page(client)
    assert all(item["attachments_count"] == 1 for item in items)
