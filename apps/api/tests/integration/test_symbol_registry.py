"""Словарь `symbols` против настоящего Postgres — развилки 3 и 4 тикета S1-07.

Разбор имени чистый и проверен в `tests/unit/test_symbols.py`. Здесь единственное, ради
чего нужна база: символ заводится при первом появлении и после этого не меняется
автоматикой. Оба утверждения ломаются молча — правка человека возвращается к машинному
значению, а перекрывающийся батч плодит вторую строку, — поэтому проверяются состоянием
таблицы, а не тем, что вернула функция.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from time import monotonic
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.community.postgres import PostgresContainer

from alembic import command
from app.core.config import get_settings
from app.core.db import get_engine, get_session_factory
from app.domains.ingest.models import Symbol
from app.domains.ingest.symbol_registry import (
    SOURCE_AUTO,
    SOURCE_USER,
    RegisteredSymbol,
    ensure_symbols,
)

pytestmark = pytest.mark.integration

API_DIR = Path(__file__).resolve().parents[2]

# Символ, у которого машинное имя заведомо отличается от правильного: брокер зовёт золото
# `GOLD.m`, эвристика SPEC.md 6.4 очистит его до `GOLD` и не узнает, а человек поправит на
# `XAUUSD`. На такой паре видно, чьё значение победило, — на `EURUSD.m` не видно.
GOLD_RAW = "GOLD.m"
GOLD_MACHINE_NORM = "GOLD"
GOLD_USER_NORM = "XAUUSD"

LOCK_WAIT_TIMEOUT_SECONDS = 15.0
LOCK_WAIT_POLL_SECONDS = 0.02

# Ожидание замка видно в `pg_locks`: замок запрошен, но не выдан. Вставка, упёршаяся в
# уникальный индекс, ждёт транзакцию-вставщика именно так.
_LOCK_WAITERS = text("select count(*) from pg_locks where not granted and pid = :pid")


@pytest.fixture(scope="module")
def postgres() -> Iterator[PostgresContainer]:
    # Имя с маркером _test: иначе guard из core/db.py не даст создать движок.
    with PostgresContainer("postgres:16-alpine", dbname="td_test") as container:
        yield container


@pytest.fixture(scope="module")
def schema(postgres: PostgresContainer) -> Iterator[None]:
    """Миграции — один раз на модуль; между тестами чистятся только данные.

    `get_settings.cache_clear()` вокруг обеих команд обязателен: `alembic/env.py` читает
    URL через `lru_cache`, а функциональная фикстура `reset_app_state` до setup и teardown
    модуля не дотягивается.
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
    local_env: pytest.MonkeyPatch, schema: None, postgres: PostgresContainer
) -> pytest.MonkeyPatch:
    url = postgres.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    local_env.setenv("DATABASE_URL", url)
    return local_env


@pytest.fixture(autouse=True)
async def clean_state(live_env: pytest.MonkeyPatch) -> AsyncIterator[None]:
    async with get_engine().begin() as connection:
        await connection.execute(text("truncate symbols restart identity cascade"))
    yield


async def rows() -> list[dict[str, Any]]:
    """Строки `symbols` целиком, включая `id`: по нему видно пересоздание строки."""
    async with get_session_factory()() as session:
        found = await session.execute(
            select(Symbol.id, Symbol.raw, Symbol.norm, Symbol.asset_class, Symbol.source).order_by(
                Symbol.raw
            )
        )
        return [dict(row) for row in found.mappings()]


async def raws_in_insertion_order() -> list[str]:
    """Сырые имена в порядке, в котором строки легли в таблицу.

    `symbols.id` — обычный serial, и внутри одного многострочного INSERT он раздаётся в
    порядке VALUES. Это единственный наблюдаемый снаружи след того порядка, ради которого
    в `ensure_symbols` стоит `sorted`.
    """
    async with get_session_factory()() as session:
        found = await session.execute(select(Symbol.raw).order_by(Symbol.id))
        return list(found.scalars())


async def register(raw_symbols: list[str]) -> dict[str, RegisteredSymbol]:
    """Один синк: своя сессия, своя транзакция, коммит — как это сделает S1-04."""
    async with get_session_factory()() as session:
        registered = await ensure_symbols(session, raw_symbols)
        await session.commit()
        return registered


async def backend_pid(session: AsyncSession) -> int:
    """`pid` бэкенда Postgres, обслуживающего эту сессию.

    Заодно открывает соединение: дальше сессия обязана ходить в базу тем же бэкендом,
    иначе в `pg_locks` найдётся не она.
    """
    pid = await session.scalar(text("select pg_backend_pid()"))
    assert isinstance(pid, int)
    return pid


async def waiting_for_a_lock(watcher: AsyncSession, pid: int, running: asyncio.Task[Any]) -> bool:
    """Ждёт, пока `pid` встанет в очередь за замком. Опрос обрывается, если задача успела
    завершиться: ждать замка от того, кто уже вернул ответ, бессмысленно."""
    deadline = monotonic() + LOCK_WAIT_TIMEOUT_SECONDS
    while monotonic() < deadline:
        waiting = await watcher.scalar(_LOCK_WAITERS, {"pid": pid})
        if waiting or running.done():
            return bool(waiting)
        await asyncio.sleep(LOCK_WAIT_POLL_SECONDS)
    return False


async def put_user_row(session: AsyncSession) -> None:
    """Ручная правка человека (UI появится на этапе 4, колонка есть сейчас)."""
    session.add(Symbol(raw=GOLD_RAW, norm=GOLD_USER_NORM, asset_class="metal", source=SOURCE_USER))
    await session.flush()


# --- первое появление ----------------------------------------------------------------


async def test_first_sync_creates_a_row_per_raw_symbol() -> None:
    registered = await register(["EURUSD.m", "XYZ.m"])

    assert registered["EURUSD.m"] == RegisteredSymbol(
        raw="EURUSD.m", norm="EURUSD", asset_class="fx", source=SOURCE_AUTO
    )
    # Незнакомый инструмент не теряется: очищенное имя и `other` (SPEC.md 6.4).
    assert registered["XYZ.m"] == RegisteredSymbol(
        raw="XYZ.m", norm="XYZ", asset_class="other", source=SOURCE_AUTO
    )
    assert [(row["raw"], row["norm"], row["source"]) for row in await rows()] == [
        ("EURUSD.m", "EURUSD", SOURCE_AUTO),
        ("XYZ.m", "XYZ", SOURCE_AUTO),
    ]


async def test_symbols_of_different_brokers_stay_separate_rows_with_one_name() -> None:
    """Ради чего вся задача: разные `raw` одного инструмента дают один `norm`.

    `raw` уникален, поэтому строк три; журнал склеивает их по `norm`, и фильтр «по EURUSD»
    собирает все три счёта.
    """
    registered = await register(["EURUSD.m", "EURUSD.raw", "EURUSD_i"])

    assert {item.norm for item in registered.values()} == {"EURUSD"}
    assert len(await rows()) == 3


async def test_empty_batch_creates_nothing() -> None:
    assert await register([]) == {}
    assert await rows() == []


async def test_every_requested_symbol_comes_back() -> None:
    """S1-04 берёт `symbol_norm` из этого отображения: пропуск ключа — падение ингеста.

    Регистр сырых символов не схлопывается: `EURUSD.m` и `eurusd.m` — разные строки
    брокера, и решать за него, что это одно и то же, здесь нечем.
    """
    registered = await register(["EURUSD.m", "EURUSD.m", "eurusd.m"])

    assert sorted(registered) == ["EURUSD.m", "eurusd.m"]
    assert {item.norm for item in registered.values()} == {"EURUSD"}


# --- порядок вставки -----------------------------------------------------------------


async def test_rows_are_inserted_in_one_canonical_order_whatever_the_batch_order() -> None:
    """Все синки вставляют символы в одном порядке — защита от взаимоблокировки.

    Многострочный INSERT берёт строчные замки в порядке VALUES: два синка с
    пересекающимися наборами, идущие навстречу друг другу, зацепились бы намертво, и
    Postgres оборвал бы один из них по `deadlock_timeout`. Общий порядок это исключает.

    Сам дедлок здесь не воспроизводится: обе вставки — по одному оператору, изнутри
    оператора клиенту вклиниться нечем, и такой тест держался бы на тайминге. Проверяется
    то, на чём защита стоит, — что порядок вставки задан набором, а не порядком батча.
    """
    await register(["XAUUSD.m", "EURUSD.m", "GBPUSD.m"])

    assert await raws_in_insertion_order() == ["EURUSD.m", "GBPUSD.m", "XAUUSD.m"]


# --- транзакцией владеет вызывающий --------------------------------------------------


async def test_nothing_is_committed_by_ensure_symbols_itself() -> None:
    """S1-04 вставит сделки и пересоберёт позиции одной транзакцией (SPEC.md 5.3).

    Коммит внутри `ensure_symbols` разрезал бы её пополам, и откат ингеста оставил бы в
    базе символы от неудавшегося батча. Отличить «транзакцией владеет вызывающий» от
    «здесь уже закоммичено» можно только откатом: до него оба варианта выглядят
    одинаково — строка видна своей же сессии в обоих.
    """
    async with get_session_factory()() as session:
        registered = await ensure_symbols(session, ["EURUSD.m", "XYZ.m"])
        assert sorted(registered) == ["EURUSD.m", "XYZ.m"], "вставка не состоялась вовсе"
        await session.rollback()

    assert await rows() == []


async def test_rollback_after_ensure_symbols_leaves_earlier_rows_alone() -> None:
    """Откат неудавшегося батча отматывает только его: чужой коммит он не трогает.

    Иначе тест выше проходил бы и на реализации, которая роняет таблицу целиком.
    """
    await register(["EURUSD.m"])
    before = await rows()

    async with get_session_factory()() as session:
        await ensure_symbols(session, ["EURUSD.m", "XYZ.m"])
        await session.rollback()

    assert await rows() == before


# --- идемпотентность -----------------------------------------------------------------


async def test_second_sync_neither_duplicates_nor_rewrites() -> None:
    """Перекрывающиеся батчи — норма: коллектор перезапрашивает окно (SPEC.md 8)."""
    await register(["EURUSD.m", "XYZ.m"])
    before = await rows()

    again = await register(["EURUSD.m", "XYZ.m"])

    assert await rows() == before
    assert {raw: item.norm for raw, item in again.items()} == {"EURUSD.m": "EURUSD", "XYZ.m": "XYZ"}


async def test_new_symbol_in_an_overlapping_batch_leaves_the_old_rows_alone() -> None:
    await register(["EURUSD.m"])
    before = await rows()

    await register(["EURUSD.m", "GBPUSD.m"])

    after = await rows()
    assert after[:1] == before, "строка существующего символа пересоздана"
    assert [row["raw"] for row in after] == ["EURUSD.m", "GBPUSD.m"]


# --- ручная правка -------------------------------------------------------------------


async def test_manual_correction_survives_the_next_sync() -> None:
    """SPEC.md 6.4: `source='user'` не перезаписывается автоматикой.

    Без этого первый же синк после правки вернул бы машинное имя, и человек решил бы, что
    правка не сохранилась. UI появится на этапе 4 — правило нужно раньше него.
    """
    async with get_session_factory()() as session:
        await put_user_row(session)
        await session.commit()
    before = await rows()

    registered = await register([GOLD_RAW])

    assert registered[GOLD_RAW] == RegisteredSymbol(
        raw=GOLD_RAW, norm=GOLD_USER_NORM, asset_class="metal", source=SOURCE_USER
    )
    assert await rows() == before
    assert before[0]["norm"] != GOLD_MACHINE_NORM


async def test_position_would_be_built_under_the_name_the_user_chose() -> None:
    """Возвращается то, что лежит в БД, а не пересчитанное: `positions.symbol_norm` берётся
    отсюда, и правка человека обязана доехать до строки журнала, а не остаться в словаре."""
    async with get_session_factory()() as session:
        await put_user_row(session)
        await session.commit()

    async with get_session_factory()() as session:
        registered = await ensure_symbols(session, [GOLD_RAW])

    assert registered[GOLD_RAW].norm == GOLD_USER_NORM


async def test_symbol_created_by_a_parallel_sync_is_not_overwritten() -> None:
    """Та же гарантия, но в одновременности, — иначе она держится на порядке действий.

    Последовательный тест выше проходит и на реализации «прочитал, не нашёл, записал
    поверх»: ко второму синку правка уже видна, и записывать поверх нечего. Здесь строка
    появляется **после** того, как синк её не нашёл, и до того, как он вставил свою: ровно
    окно, ради которого стоит `ON CONFLICT DO NOTHING`.

    Одновременность не подгадывается таймингом, а проверяется ассертом: вставка синка
    упирается в уникальный индекс и ждёт чужую транзакцию, `pg_locks` показывает её
    ждущей — и только после этого правка коммитится. Без ассерта «гонка была и защита
    сработала» и «гонки не было вовсе» дали бы один и тот же зелёный результат.

    Уникально этим тестом ловится замена `DO NOTHING` на `DO UPDATE`: под ней синк так же
    ждёт замка, а проснувшись — затирает правку человека машинным именем.
    """
    factory = get_session_factory()
    async with factory() as watcher, factory() as manual, factory() as sync:
        pid = await backend_pid(sync)
        await put_user_row(manual)
        task = asyncio.create_task(ensure_symbols(sync, [GOLD_RAW]))
        try:
            waited = await waiting_for_a_lock(watcher, pid, task)
        finally:
            # Правка коммитится при любом исходе, иначе синк останется ждать в базе.
            await manual.commit()
        registered = await task
        await sync.commit()

    assert waited, (
        "вставка синка не встала в очередь за замком: гонки не было, и результат ниже "
        "ничего не доказывает"
    )
    assert registered[GOLD_RAW].norm == GOLD_USER_NORM
    assert [(row["norm"], row["source"]) for row in await rows()] == [(GOLD_USER_NORM, SOURCE_USER)]
