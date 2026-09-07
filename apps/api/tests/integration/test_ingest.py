"""`POST /ingest/deals` против настоящих Postgres и Redis — DoD S1-04.

Здесь впервые проверяется путь «данные брокера → строки в базе» целиком. Всё, что до сих
пор жило чистыми функциями (`normalizer.py`, `position_builder.py`), встречается с
транзакцией, повторами и чужими строками, и почти ничто из проверяемого ниже не ломается
громко.

Четыре утверждения, ради которых этот файл существует, и все четыре читаются из состояния
таблиц, а не из ответа эндпоинта:

* **`positions.id` переживает пересборку**, а вместе с ним — заметка и рефлексия. `S1-03`
  доказал идемпотентность на уровне чистой функции; что UPSERT сохраняет строку, до этого
  места не проверял никто.
* **инструмент-призрак не заводится**: у депозита символ пустой, и наивный `ensure_symbols`
  по всем сделкам батча положил бы в `symbols` строку с `raw = ''`.
* **позиция собирается по всем сделкам счёта**, а не по пришедшим в батче: комиссия
  приезжает следующим окном синка, когда торговые сделки уже в базе.
* **перекрывающиеся батчи дают то же, что один общий** — коллектор перезапрашивает окно
  намеренно (SPEC.md 8.2), и повтор обязан быть бесплатным.
"""

from __future__ import annotations

import io
import json
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from arq.jobs import JobDef
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from alembic import command
from app.core.config import get_settings
from app.core.db import get_engine, get_session_factory
from app.core.queue import get_queue
from app.core.redis import get_redis
from app.domains.accounts import service as accounts
from app.domains.ingest.schemas import MAX_DEALS_PER_BATCH
from app.worker import REFRESH_DAILY_STATS_NAME

pytestmark = pytest.mark.integration

API = "/api/v1"
API_DIR = Path(__file__).resolve().parents[2]
FIXTURES = API_DIR / "tests/fixtures/deals"

INGEST = f"{API}/ingest/deals"
COLLECTOR_TOKEN = "test-collector-token"
AUTH = {"authorization": f"Bearer {COLLECTOR_TOKEN}"}

EMAIL = "ingest-owner@example.test"
OFFSET = 120

_TABLES = (
    "users, trading_accounts, account_credentials, symbols, "
    "deals, positions, sync_runs, journal_entries, reflections, attachments, tags, daily_stats"
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
    """Коллектор: сервисный токен, без сессии и без `Origin` (он не браузер)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=AUTH) as opened:
        yield opened


@pytest.fixture
async def failing_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Клиент, который доносит 500 как ответ, а не как исключение транспорта."""
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test", headers=AUTH) as opened:
        yield opened


@pytest.fixture
def log_stream(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Поток обработчика логов приложения — так же, как в `test_collector.py`."""
    stream = io.StringIO()
    monkeypatch.setattr(logging.getLogger().handlers[0], "stream", stream)
    return stream


@pytest.fixture
async def account(app: FastAPI) -> UUID:
    """Счёт со владельцем. Заводится напрямую: логин коллектору здесь не нужен."""
    account_id = uuid4()
    async with get_session_factory()() as session:
        user_id = uuid4()
        await session.execute(
            text(
                "insert into users (id, email, timezone, day_boundary_hour) "
                "values (:id, :email, 'Europe/Moscow', 0)"
            ),
            {"id": user_id, "email": EMAIL},
        )
        await session.execute(
            text(
                "insert into trading_accounts "
                "(id, user_id, label, color, platform, server, login, currency, status) "
                "values (:id, :user_id, 'Боевой', '#4f46e5', 'mt5', 'EGlobal', 900001, "
                "'USD', 'pending')"
            ),
            {"id": account_id, "user_id": user_id},
        )
        await session.commit()
    return account_id


# --- вспомогательное -----------------------------------------------------------


def fixture(name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return document


def batches(name: str, account_id: UUID) -> list[dict[str, Any]]:
    """Батчи фикстуры, переадресованные на счёт теста."""
    prepared = []
    for batch in fixture(name)["batches"]:
        prepared.append({**batch, "account_id": str(account_id)})
    return prepared


def batch_of(
    deals: list[dict[str, Any]],
    account_id: UUID,
    *,
    open_positions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "account_id": str(account_id),
        "source": "collector",
        "server_utc_offset_minutes": OFFSET,
        "account_info": {
            "currency": "USD",
            "margin_mode": "hedging",
            "balance": 343.1,
            "equity": 343.1,
        },
        "deals": deals,
        "open_positions": open_positions or [],
    }


async def rows(statement: str, **params: Any) -> list[dict[str, Any]]:
    async with get_session_factory()() as session:
        found = await session.execute(text(statement), params)
        return [dict(row) for row in found.mappings()]


async def positions_of(account_id: UUID) -> list[dict[str, Any]]:
    return await rows(
        "select id, position_id, symbol_raw, symbol_norm, direction, status, "
        "open_time, close_time, volume_opened::text, volume_closed::text, "
        "avg_entry_price::text, avg_exit_price::text, gross_pnl::text, commission::text, "
        "swap::text, fee::text, net_pnl::text, deals_count, duration_seconds, close_reason, "
        "is_manual from positions where account_id = :account_id order by position_id",
        account_id=account_id,
    )


def as_expected(row: dict[str, Any]) -> dict[str, Any]:
    """Строка `positions` в терминах поля `expected` фикстур `S1-03`."""
    return {
        "position_id": row["position_id"],
        "symbol_raw": row["symbol_raw"],
        "direction": row["direction"],
        "status": row["status"],
        "open_time": row["open_time"].isoformat().replace("+00:00", "Z"),
        "close_time": (
            None
            if row["close_time"] is None
            else row["close_time"].isoformat().replace("+00:00", "Z")
        ),
        "volume_opened": row["volume_opened"],
        "volume_closed": row["volume_closed"],
        "avg_entry_price": row["avg_entry_price"],
        "avg_exit_price": row["avg_exit_price"],
        "gross_pnl": row["gross_pnl"],
        "commission": row["commission"],
        "swap": row["swap"],
        "fee": row["fee"],
        "net_pnl": row["net_pnl"],
        "deals_count": row["deals_count"],
        "duration_seconds": row["duration_seconds"],
        "close_reason": row["close_reason"],
    }


async def send(client: AsyncClient, batch: dict[str, Any]) -> dict[str, Any]:
    response = await client.post(INGEST, json=batch)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def queued() -> list[JobDef]:
    return list(await (await get_queue()).queued_jobs())


def events(stream: io.StringIO, name: str) -> list[dict[str, Any]]:
    found = []
    for line in stream.getvalue().splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event") == name:
            found.append(record)
    return found


# --- сделки и позиции ----------------------------------------------------------


async def test_batch_writes_deals_and_the_position_the_builder_promised(
    client: AsyncClient, account: UUID
) -> None:
    """Строка `positions` в базе совпадает с `expected` фикстуры S1-03 — поле в поле."""
    document = fixture("real-simple-long.json")
    body = await send(client, batches("real-simple-long.json", account)[0])

    assert body["received"] == 2
    assert body["inserted"] == 2
    assert body["duplicates"] == 0
    assert body["positions_rebuilt"] == 1
    assert isinstance(body["sync_run_id"], int)

    stored = await positions_of(account)
    assert [as_expected(row) for row in stored] == document["expected"]
    assert stored[0]["symbol_norm"] == "USDJPY"
    assert stored[0]["is_manual"] is False


async def test_the_same_batch_twice_adds_nothing(client: AsyncClient, account: UUID) -> None:
    """Идемпотентность вставки: второй прогон не плодит ни сделок, ни позиций."""
    batch = batches("real-simple-long.json", account)[0]
    await send(client, batch)
    before = await positions_of(account)

    second = await send(client, batch)

    assert (second["received"], second["inserted"], second["duplicates"]) == (2, 0, 2)
    after = await positions_of(account)
    assert after == before
    assert len(await rows("select id from deals where account_id = :a", a=account)) == 2


async def test_overlapping_batches_give_the_same_position_as_one(
    client: AsyncClient, account: UUID
) -> None:
    """Коллектор перезапрашивает окно `last_sync_at − 24h`: средняя сделка приезжает дважды."""
    document = fixture("real-two-batches-overlap.json")
    prepared = batches("real-two-batches-overlap.json", account)

    first = await send(client, prepared[0])
    second = await send(client, prepared[1])

    assert first["inserted"] == len(prepared[0]["deals"])
    assert second["duplicates"] > 0, "перекрытия в фикстуре нет — тест ничего не проверяет"
    stored = await positions_of(account)
    assert [as_expected(row) for row in stored] == document["expected"]


async def test_deal_ticket_repeated_inside_one_batch_counts_as_duplicate(
    client: AsyncClient, account: UUID
) -> None:
    """Повтор внутри одного батча — тоже дубль, а не вторая сделка."""
    deals = batches("real-simple-long.json", account)[0]["deals"]
    body = await send(client, batch_of([*deals, deals[0]], account))

    assert (body["received"], body["inserted"], body["duplicates"]) == (3, 2, 1)
    assert len(await rows("select id from deals where account_id = :a", a=account)) == 2


# --- пользовательский слой -----------------------------------------------------


async def test_user_layer_survives_a_rebuild(client: AsyncClient, account: UUID) -> None:
    """Заметка и рефлексия переживают пересборку и остаются на той же позиции.

    Главный тест файла. Ломается это молча и необратимо: пересоздай UPSERT `positions.id`
    — и записи пользователя уносит каскадом, а в журнале остаётся чистая строка, про
    которую никто не вспомнит, что в ней было.
    """
    prepared = batches("real-two-batches-overlap.json", account)
    await send(client, prepared[0])
    position = (await positions_of(account))[0]
    position_id = position["id"]

    async with get_session_factory()() as session:
        await session.execute(
            text(
                "insert into journal_entries (position_id, notes, tags, updated_at) "
                "values (:id, :notes, array['trend'], now())"
            ),
            {"id": position_id, "notes": "план сработал"},
        )
        await session.execute(
            text(
                "insert into reflections (position_id, setup_grade, confidence, updated_at) "
                "values (:id, 'A', 4, now())"
            ),
            {"id": position_id},
        )
        await session.commit()

    # Второй батч меняет позицию по-настоящему: приезжает выход, статус становится closed.
    await send(client, prepared[1])

    after = (await positions_of(account))[0]
    assert after["id"] == position_id, "UPSERT пересоздал строку — пользовательский слой унесён"
    assert after["status"] == "closed"

    entries = await rows("select position_id, notes, tags from journal_entries")
    reflections = await rows("select position_id, setup_grade, confidence from reflections")
    assert entries == [{"position_id": position_id, "notes": "план сработал", "tags": ["trend"]}]
    assert reflections == [{"position_id": position_id, "setup_grade": "A", "confidence": 4}]


# --- символы -------------------------------------------------------------------


async def test_a_deposit_does_not_create_a_ghost_instrument(
    client: AsyncClient, account: UUID
) -> None:
    """У неторговой операции символ пустой, и в `symbols` он попасть не должен (X-44).

    Проверяется состоянием таблицы, а не отсутствием ошибки: пустой `raw` завёлся бы
    молча и остался бы в словаре навсегда — строку оттуда никто не удаляет.
    """
    document = fixture("real-deposit-is-not-a-position.json")
    body = await send(client, batches("real-deposit-is-not-a-position.json", account)[0])

    assert body["inserted"] == 3, "депозит обязан сохраниться в deals для сверки баланса"
    assert body["positions_rebuilt"] == 1

    symbols = await rows("select raw, norm, source from symbols order by raw")
    assert symbols == [{"raw": "USDJPY", "norm": "USDJPY", "source": "auto"}]
    assert [as_expected(row) for row in await positions_of(account)] == document["expected"]


# --- корректировки, приехавшие отдельным окном ---------------------------------


async def test_an_adjustment_alone_waits_for_its_trades(
    client: AsyncClient, account: UUID, log_stream: io.StringIO
) -> None:
    """Группа из одних корректировок позицию не создаёт и батч не роняет.

    Сборщик такую группу отвергает (`PositionBuildError`) — для чистой функции это верно,
    направление брать неоткуда. Здесь она штатна: у неё просто ещё нет входа.
    """
    deals = fixture("synthetic-adjustment-other.json")["batches"][0]["deals"]
    adjustment = [deal for deal in deals if deal["type"] == 7]

    body = await send(client, batch_of(adjustment, account))

    assert (body["inserted"], body["positions_rebuilt"]) == (1, 0)
    assert await positions_of(account) == []
    skipped = events(log_stream, "ingest.position_unbuildable")
    assert [record["position_id"] for record in skipped] == [800021]


async def test_a_position_is_built_from_every_deal_in_the_database(
    client: AsyncClient, account: UUID
) -> None:
    """Комиссия из прошлого окна доезжает до `net_pnl`, а не теряется.

    Собери позицию по сделкам батча — в `net_pnl` не хватило бы 1,25, и заметить это
    можно было бы только сверкой с отчётом терминала недели спустя (`S1-12`).
    """
    document = fixture("synthetic-adjustment-other.json")
    deals = document["batches"][0]["deals"]
    adjustment = [deal for deal in deals if deal["type"] == 7]
    trades = [deal for deal in deals if deal["type"] in (0, 1)]

    await send(client, batch_of(adjustment, account))
    body = await send(client, batch_of(trades, account))

    assert body["positions_rebuilt"] == 1
    assert [as_expected(row) for row in await positions_of(account)] == document["expected"]


# --- открытые позиции ----------------------------------------------------------


async def test_an_open_position_keeps_costs_not_floating_profit(
    client: AsyncClient, account: UUID
) -> None:
    """Батч приносит `profit = 137.50` в `open_positions`; в позиции его быть не должно."""
    document = fixture("synthetic-open-position.json")
    await send(client, batches("synthetic-open-position.json", account)[0])

    assert [as_expected(row) for row in await positions_of(account)] == document["expected"]


async def test_an_open_position_without_deals_becomes_a_row(
    client: AsyncClient, account: UUID
) -> None:
    """SPEC.md 5.3, пункт 5: история ещё не догружена, а позиция на счёте уже есть.

    Проверить это настоящими данными нечем — открытых позиций в выгрузке 7 сентября
    2026 нет ни одной (`docs/mt5-assumptions.md`).
    """
    record = fixture("synthetic-open-position.json")["batches"][0]["open_positions"][0]

    body = await send(client, batch_of([], account, open_positions=[record]))

    assert (body["received"], body["inserted"], body["positions_rebuilt"]) == (0, 0, 1)
    stored = await positions_of(account)
    assert as_expected(stored[0]) == {
        "position_id": 800031,
        "symbol_raw": "GBPUSD",
        "direction": "long",
        "status": "open",
        # time_server 08:30 при смещении +120 — это 06:30 UTC.
        "open_time": "2026-03-06T06:30:00Z",
        "close_time": None,
        "volume_opened": "0.20000000",
        "volume_closed": "0.00000000",
        "avg_entry_price": "1.30000000",
        "avg_exit_price": None,
        "gross_pnl": "0.00",
        "commission": "0.00",
        "swap": "0.00",
        "fee": "0.00",
        # Не 137.50: плавающий результат в net_pnl не попадает никогда (S1-03).
        "net_pnl": "0.00",
        "deals_count": 0,
        "duration_seconds": None,
        "close_reason": None,
    }
    assert stored[0]["symbol_norm"] == "GBPUSD"


async def test_deals_arriving_later_rebuild_the_row_in_place(
    client: AsyncClient, account: UUID
) -> None:
    """Строка, заведённая из `open_positions`, пересобирается по сделкам и сохраняет `id`."""
    prepared = batches("synthetic-open-position.json", account)[0]
    record = prepared["open_positions"][0]

    await send(client, batch_of([], account, open_positions=[record]))
    empty = (await positions_of(account))[0]

    await send(client, prepared)

    rebuilt = (await positions_of(account))[0]
    assert rebuilt["id"] == empty["id"]
    assert rebuilt["deals_count"] == 1
    assert rebuilt["net_pnl"] == "-1.40"


# --- карточка счёта, sync_runs и очередь ---------------------------------------


async def test_a_successful_batch_updates_the_account_card(
    client: AsyncClient, account: UUID
) -> None:
    """SPEC.md 5.3, пункт 3: тип счёта, смещение, время синка и статус."""
    await send(client, batches("real-simple-long.json", account)[0])

    card = (await rows("select * from trading_accounts where id = :a", a=account))[0]
    assert card["account_type"] == "hedging"
    assert card["server_utc_offset_minutes"] == OFFSET
    assert card["status"] == accounts.STATUS_CONNECTED
    assert card["status_message"] is None
    assert card["last_sync_at"] is not None


async def test_a_successful_batch_records_its_sync_run(client: AsyncClient, account: UUID) -> None:
    body = await send(client, batches("real-simple-long.json", account)[0])

    runs = await rows("select * from sync_runs where account_id = :a", a=account)
    assert len(runs) == 1
    run = runs[0]
    assert run["id"] == body["sync_run_id"]
    assert (run["source"], run["deals_received"], run["deals_new"]) == ("collector", 2, 2)
    assert run["positions_rebuilt"] == 1
    assert run["server_utc_offset_minutes"] == OFFSET
    assert run["error"] is None
    assert run["finished_at"] is not None


async def test_a_successful_batch_queues_the_daily_stats_refresh(
    client: AsyncClient, account: UUID
) -> None:
    """SPEC.md 5.3, пункт 6. Читается из очереди, а не из лога: заявление тут не считается.

    В задачу уезжает отрезок времени тронутых сделок, а не список дней: правило торгового
    дня живёт в `domains/analytics`, и ингест не вправе прочитать его второй раз.
    """
    await send(client, batches("real-simple-long.json", account)[0])

    jobs = await queued()
    assert [job.function for job in jobs] == [REFRESH_DAILY_STATS_NAME]
    assert jobs[0].args == (str(account),)
    # Крайние `time_utc` двух сделок фикстуры: 14:55:05 и 15:02:20 при смещении +120.
    assert jobs[0].kwargs == {"within": ["2025-11-27T12:55:05+00:00", "2025-11-27T13:02:20+00:00"]}


async def test_an_empty_batch_queues_nothing(client: AsyncClient, account: UUID) -> None:
    """Пустой батч — штатный «нового нет». Гонять пересчёт по нему незачем."""
    await send(client, batch_of([], account))

    assert await queued() == []


async def test_a_repeated_batch_rebuilds_nothing_and_queues_nothing(
    client: AsyncClient, account: UUID
) -> None:
    """Батч перекрытия — «ничего не изменил» в том виде, в каком это бывает в жизни.

    Коллектор перезапрашивает окно `last_sync_at − 24h` каждые 60 секунд (SPEC.md 8.2),
    то есть повтор приходит постоянно. Считай пересборку по **всем** сделкам батча — и у
    счёта, торговавшего за сутки, каждый тик синка гнал бы полную пересборку и ставил бы
    задачу пересчёта. Затронуты только позиции **новых** сделок (SPEC.md 5.3, пункт 4).
    """
    batch = batches("real-simple-long.json", account)[0]
    await send(client, batch)
    await get_redis().flushdb()

    repeated = await send(client, batch)

    assert (repeated["inserted"], repeated["duplicates"]) == (0, 2)
    assert repeated["positions_rebuilt"] == 0
    assert await queued() == []


async def test_a_paused_account_still_accepts_the_batch(client: AsyncClient, account: UUID) -> None:
    """Пауза — просьба не ходить к брокеру, а не запрет хранить уже полученные факты.

    Держится это на раннем `return` в `accounts.apply_sync_result`: снять его — и пауза
    начнёт молча сниматься первым же синком, а данные при этом продолжат приходить.
    """
    async with get_engine().begin() as connection:
        await connection.execute(
            text("update trading_accounts set status = 'paused' where id = :a"), {"a": account}
        )

    body = await send(client, batches("real-simple-long.json", account)[0])

    assert (body["inserted"], body["positions_rebuilt"]) == (2, 1)
    card = (await rows("select status, last_sync_at from trading_accounts"))[0]
    assert card["status"] == accounts.STATUS_PAUSED, "синк снял паузу"
    assert card["last_sync_at"] is not None, "синк был, а в карточке счёта его нет"


async def test_unavailable_queue_does_not_lose_the_batch(
    client: AsyncClient, account: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Сделки уже зафиксированы: ронять ответ из-за кэша, который никто не читает, нельзя."""
    from app.core import queue as queue_module

    async def unreachable() -> Any:
        raise ConnectionError("redis недоступен")

    monkeypatch.setattr(queue_module, "get_queue", unreachable)
    body = await send(client, batches("real-simple-long.json", account)[0])

    assert body["inserted"] == 2
    assert len(await positions_of(account)) == 1


# --- отказы --------------------------------------------------------------------


async def test_without_the_service_token_nothing_is_accepted(app: FastAPI, account: UUID) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anonymous:
        response = await anonymous.post(INGEST, json=batch_of([], account))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert await rows("select id from sync_runs") == []


async def test_an_unknown_account_is_404_and_leaves_no_run(client: AsyncClient) -> None:
    """Строку `sync_runs` вешать не на что: её `account_id` ссылается на реальный счёт."""
    response = await client.post(INGEST, json=batch_of([], uuid4()))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == accounts.ACCOUNT_NOT_FOUND_CODE
    assert await rows("select id from sync_runs") == []


async def test_an_archived_account_refuses_the_batch_visibly(
    client: AsyncClient, account: UUID
) -> None:
    """Отказ виден человеку: историю синков показывает экран счёта (`S1-11`)."""
    async with get_engine().begin() as connection:
        await connection.execute(
            text("update trading_accounts set status = 'archived' where id = :a"), {"a": account}
        )

    response = await client.post(INGEST, json=batches("real-simple-long.json", account)[0])

    assert response.status_code == 422
    assert response.json()["error"]["code"] == accounts.ACCOUNT_ARCHIVED_CODE
    runs = await rows("select deals_received, deals_new, error from sync_runs")
    assert runs == [{"deals_received": 2, "deals_new": 0, "error": "Счёт в архиве: батч не принят"}]
    assert await rows("select id from deals") == []


async def test_a_batch_over_the_limit_is_413_not_400(client: AsyncClient, account: UUID) -> None:
    """SPEC.md 5.3, пункт 1. Порог живёт в маршруте: схема ответила бы 400.

    Батч валиден по форме целиком — иначе тест доказывал бы не то: «слишком большой»
    и «неправильной формы» это разные утверждения, и проверяется первое.
    """
    template = batches("real-simple-long.json", account)[0]["deals"][0]
    deals = [
        {**template, "ticket": template["ticket"] + index, "position_id": 700000 + index}
        for index in range(MAX_DEALS_PER_BATCH + 1)
    ]

    response = await client.post(INGEST, json=batch_of(deals, account))

    assert response.status_code == 413
    error = response.json()["error"]
    assert error["code"] == "payload_too_large"
    assert error["details"] == {"received": MAX_DEALS_PER_BATCH + 1, "limit": MAX_DEALS_PER_BATCH}
    assert await rows("select id from deals") == []
    runs = await rows("select deals_received, error from sync_runs")
    assert runs == [
        {
            "deals_received": MAX_DEALS_PER_BATCH + 1,
            "error": f"Батч превысил предел в {MAX_DEALS_PER_BATCH} сделок и не принят",
        }
    ]


async def test_the_limit_itself_is_accepted(client: AsyncClient, account: UUID) -> None:
    """Ровно 5000 — это «не больше», а не «меньше». Заодно проверяется, что вставка
    разбита на куски: одним оператором столько параметров Postgres не примет.
    """
    template = batches("real-simple-long.json", account)[0]["deals"][0]
    deals = [
        {**template, "ticket": template["ticket"] + index, "position_id": 700000 + index}
        for index in range(MAX_DEALS_PER_BATCH)
    ]

    body = await send(client, batch_of(deals, account))

    assert body["inserted"] == MAX_DEALS_PER_BATCH
    assert body["positions_rebuilt"] == MAX_DEALS_PER_BATCH


async def test_a_body_over_the_cap_never_reaches_the_parser(
    client: AsyncClient, account: UUID
) -> None:
    """Потолок на байты стоит до разбора JSON (`core/body_limit.py`).

    Тело здесь заведомо не разбирается как батч: если бы 413 отдавала проверка после
    разбора, ответ был бы `400 validation_error`.
    """
    from app.main import INGEST_MAX_BODY_BYTES

    payload = b'{"junk": "' + b"x" * (INGEST_MAX_BODY_BYTES + 1) + b'"}'
    response = await client.post(
        INGEST, content=payload, headers={**AUTH, "content-type": "application/json"}
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_a_failure_rolls_the_whole_batch_back_and_leaves_a_trace(
    failing_client: AsyncClient, account: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Развилка «транзакция при частичном отказе», решённая полным откатом.

    Отказ на пересборке обязан унести и вставленные сделки: половина батча в базе с
    непересобранными позициями не отличима в данных от целого батча. Повтор безопасен —
    коллектор перезапрашивает окно, а вставка идемпотентна.

    Строка `sync_runs` при этом остаётся: она пишется своей транзакцией, иначе откатилась
    бы вместе с батчем, и на экране счёта отказ выглядел бы как «синка просто не было».
    """
    from app.domains.ingest import service as ingest_service

    async def boom(*_: Any, **__: Any) -> int:
        raise RuntimeError("пересборка упала")

    monkeypatch.setattr(ingest_service, "_rebuild_positions", boom)
    response = await failing_client.post(INGEST, json=batches("real-simple-long.json", account)[0])

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert await rows("select id from deals") == []
    assert await rows("select id from positions") == []
    runs = await rows("select deals_received, deals_new, positions_rebuilt, error from sync_runs")
    assert runs == [
        {
            "deals_received": 2,
            "deals_new": 0,
            "positions_rebuilt": 0,
            "error": "Внутренняя ошибка при обработке батча",
        }
    ]
    # Карточка счёта тоже откатилась: успешным синк не был.
    card = (await rows("select status, last_sync_at from trading_accounts"))[0]
    assert card["status"] == accounts.STATUS_PENDING
    assert card["last_sync_at"] is None


async def test_the_failure_text_never_carries_the_exception(
    failing_client: AsyncClient, account: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`sync_runs.error` уезжает на экран счёта: текст исключения там появиться не может."""
    from app.domains.ingest import service as ingest_service

    async def boom(*_: Any, **__: Any) -> int:
        raise RuntimeError("SELECT … WHERE password = 'извне'")

    monkeypatch.setattr(ingest_service, "_rebuild_positions", boom)
    await failing_client.post(INGEST, json=batches("real-simple-long.json", account)[0])

    stored = await rows("select error from sync_runs")
    assert "извне" not in json.dumps(stored, ensure_ascii=False)


async def test_an_unsupported_currency_leaves_the_account_needing_attention(
    client: AsyncClient, account: UUID
) -> None:
    """Проверка валюты живёт в `apply_sync_result` (S1-06) и через ингест обязана работать."""
    batch = batches("real-simple-long.json", account)[0]
    batch["account_info"] = {**batch["account_info"], "currency": "EUR"}

    await send(client, batch)

    card = (await rows("select status, status_message, currency from trading_accounts"))[0]
    assert card["status"] == accounts.STATUS_NEEDS_ATTENTION
    assert card["status_message"]
    assert card["currency"] == "USD"
