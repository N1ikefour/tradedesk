"""Планировщик arq: расписание, дедупликация между процессами, обёртка над доменом."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from arq.cron import next_cron
from arq.worker import create_worker

from app import worker as worker_module
from app.core.config import Settings
from app.worker import (
    CHECK_COLLECTORS_NAME,
    CRON_JOBS,
    FUNCTIONS,
    REFRESH_DAILY_STATS_NAME,
    worker_redis_settings,
    worker_settings,
)


def test_check_collectors_registered_every_minute() -> None:
    """SPEC.md §10: cron каждую минуту. Проверяется расписанием, а не полями."""
    job = next(job for job in CRON_JOBS if job.name == CHECK_COLLECTORS_NAME)

    def following(previous: datetime) -> datetime:
        return next_cron(
            previous,
            month=job.month,
            day=job.day,
            weekday=job.weekday,
            hour=job.hour,
            minute=job.minute,
            second=job.second,
            microsecond=job.microsecond,
        )

    first = following(datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC))
    second = following(first)

    # Шаг между соседними запусками, а не расстояние от произвольного момента: arq сдвигает
    # запуск на microsecond=123456, и сравнение с круглой секундой ловило бы этот сдвиг.
    assert second - first == timedelta(minutes=1)


def test_every_cron_job_is_unique() -> None:
    """Второй worker не должен продублировать прогон (см. модульный docstring).

    `unique=True` — дефолт arq, и именно поэтому проверка нужна: снять его можно одним
    словом в вызове, а последствие — второе письмо и второй экспорт, а не второй UPDATE.
    """
    assert CRON_JOBS
    assert [job.name for job in CRON_JOBS if not job.unique] == []


def test_worker_settings_registers_cron_jobs_and_functions() -> None:
    """arq отбирает ключи по именам параметров `Worker`: опечатка молча теряет расписание.

    С задачами по вызову цена опечатки другая и хуже: api поставит задачу в очередь,
    получит job_id, а worker ответит «нет такой функции» — уже после ответа клиенту.
    """
    worker = create_worker(worker_settings())

    assert CHECK_COLLECTORS_NAME in worker.functions
    assert REFRESH_DAILY_STATS_NAME in worker.functions
    assert worker.redis_settings is not None


def test_refresh_daily_stats_has_no_schedule() -> None:
    """Пересчёт кэша ходит по вызову, а не по кругу: читателей у таблицы пока нет.

    Решение записано в `docs/metrics.md` §6, и цена ошибки тут не в лишнем CPU: cron на
    все счета скрыл бы отсутствие постановки задачи из ингеста (`S1-04`) — таблица
    выглядела бы свежей, не будучи связанной с событиями.
    """
    assert REFRESH_DAILY_STATS_NAME not in {job.name for job in CRON_JOBS}
    assert [function.__name__ for function in FUNCTIONS] == [REFRESH_DAILY_STATS_NAME]


class _FakeSession:
    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


def _capture_refresh(monkeypatch: pytest.MonkeyPatch, seen: list[tuple[Any, Any, Any]]) -> None:
    async def fake_refresh(
        _session: Any, account_id: UUID, days: Any, *, within: Any = None
    ) -> int:
        seen.append((account_id, days, within))
        return 2

    monkeypatch.setattr(worker_module, "get_session_factory", lambda: lambda: _FakeSession())
    monkeypatch.setattr(worker_module.daily_stats, "refresh", fake_refresh)


async def test_refresh_daily_stats_parses_its_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    """Очередь несёт строки — типы восстанавливаются на входе задачи, а не в домене."""
    seen: list[tuple[Any, Any, Any]] = []
    _capture_refresh(monkeypatch, seen)

    account_id = "0199a0f0-0000-7000-8000-000000000002"
    written = await worker_module.refresh_daily_stats({}, account_id, ["2026-09-02"])

    assert written == 2
    assert seen == [(UUID(account_id), [date(2026, 9, 2)], None)]


async def test_refresh_daily_stats_parses_the_utc_span(monkeypatch: pytest.MonkeyPatch) -> None:
    """`within` от ингеста: пара ISO-моментов превращается в `datetime` здесь, не в домене.

    Смещение обязано пережить очередь: `2026-09-02T23:30:00+00:00` и наивная строка того
    же вида — разные моменты, и разница в 3 часа уводит день в кэше на сутки.
    """
    seen: list[tuple[Any, Any, Any]] = []
    _capture_refresh(monkeypatch, seen)

    account_id = "0199a0f0-0000-7000-8000-000000000002"
    written = await worker_module.refresh_daily_stats(
        {}, account_id, None, ["2026-09-02T23:30:00+00:00", "2026-09-03T01:15:00+00:00"]
    )

    assert written == 2
    assert seen == [
        (
            UUID(account_id),
            None,
            (
                datetime(2026, 9, 2, 23, 30, tzinfo=UTC),
                datetime(2026, 9, 3, 1, 15, tzinfo=UTC),
            ),
        )
    ]


async def test_check_collectors_task_calls_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Обёртка открывает сессию и зовёт домен — своей логики порога у неё нет."""
    offline = [UUID("0199a0f0-0000-7000-8000-000000000001")]
    seen: list[object] = []

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

    session = FakeSession()

    async def fake_check_collectors(passed: Any) -> list[UUID]:
        seen.append(passed)
        return offline

    monkeypatch.setattr(worker_module, "get_session_factory", lambda: lambda: session)
    monkeypatch.setattr(worker_module.accounts_service, "check_collectors", fake_check_collectors)

    assert await worker_module.check_collectors({}) == len(offline)
    assert seen == [session]


def test_redis_dsn_maps_to_connection_settings(local_env: pytest.MonkeyPatch) -> None:
    """Номер базы из DSN обязан доехать до worker'а.

    Потеряется он молча: worker поднимется, начнёт слушать очередь в базе 0 и будет
    исправно рапортовать о работе, пока api ставит задачи в базу 3. Проверка дешевле
    разбирательства «планировщик жив, а задачи не идут».
    """
    local_env.setenv("REDIS_URL", "redis://redis.internal:6390/3")

    redis_settings = worker_redis_settings(Settings())

    assert (redis_settings.host, redis_settings.port, redis_settings.database) == (
        "redis.internal",
        6390,
        3,
    )
