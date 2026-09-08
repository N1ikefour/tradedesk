"""Клиент очереди arq со стороны api — `core/queue.py` (S1-04).

Две вещи, которые ломаются молча.

* **api и worker обязаны смотреть в одну базу Redis.** Разойдись они — api исправно
  вернёт `job_id`, worker исправно доложит, что жив, и ни один тест этого не покажет.
* **Недоступная очередь не должна ронять запрос.** Сделки к моменту постановки задачи
  уже зафиксированы, и `500` заставил бы коллектор повторить принятый батч ради
  пересчёта кэша, которого никто не читает.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core import queue as queue_module
from app.core.config import Settings
from app.core.queue import enqueue, queue_redis_settings
from app.worker import worker_redis_settings


def test_api_and_worker_read_the_same_redis(local_env: pytest.MonkeyPatch) -> None:
    """Номер базы из DSN обязан совпасть у обеих сторон, а не «обычно совпадать»."""
    local_env.setenv("REDIS_URL", "redis://redis.internal:6390/3")

    api = queue_redis_settings(Settings())
    worker = worker_redis_settings(Settings())

    assert (api.host, api.port, api.database) == ("redis.internal", 6390, 3)
    assert (api.host, api.port, api.database) == (worker.host, worker.port, worker.database)


async def test_an_unreachable_queue_returns_none_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unreachable() -> Any:
        raise ConnectionError("redis://user:пароль@host/0 недоступен")

    monkeypatch.setattr(queue_module, "get_queue", unreachable)

    assert await enqueue("refresh_daily_stats", "account", None) is None


async def test_a_taken_job_id_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """arq отдаёт `None`, когда задача с таким `job_id` уже в очереди."""

    class Pool:
        async def enqueue_job(self, *_: Any, **__: Any) -> None:
            return None

    async def pool() -> Any:
        return Pool()

    monkeypatch.setattr(queue_module, "get_queue", pool)

    assert await enqueue("refresh_daily_stats", "account", None) is None


async def test_the_job_id_comes_back_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class Job:
        job_id = "job-1"

    class Pool:
        def __init__(self) -> None:
            self.calls: list[tuple[Any, ...]] = []

        async def enqueue_job(self, *args: Any, **__: Any) -> Job:
            self.calls.append(args)
            return Job()

    created = Pool()

    async def pool() -> Any:
        return created

    monkeypatch.setattr(queue_module, "get_queue", pool)

    assert await enqueue("refresh_daily_stats", "account", None) == "job-1"
    assert created.calls == [("refresh_daily_stats", "account", None)]
