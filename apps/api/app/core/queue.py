"""Постановка фоновых задач в очередь arq со стороны api.

Планировщик и сами задачи живут в `app/worker.py`; здесь только клиент — пул, через
который api кладёт задачу в Redis. Отдельный модуль, а не переиспользование
`core/redis.py`: у arq свой протокол ключей и своя сериализация, и общий клиент пришлось
бы учить обеим ролям.

**Неудачная постановка задачи не роняет запрос, который её ставил.** Единственный
сегодняшний потребитель — `POST /ingest/deals`, и к моменту постановки сделки уже
зафиксированы. Уронить ответ из-за недоступного Redis означало бы заставить коллектор
повторить батч, который уже принят, ради пересчёта кэша, который никто не читает
(`docs/metrics.md` §6). Поэтому `enqueue` возвращает `None` и пишет в лог, а не бросает.
"""

from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_pool: ArqRedis | None = None


def queue_redis_settings(settings: Settings | None = None) -> RedisSettings:
    """Тот же DSN, что читает worker (`worker_redis_settings`).

    Копия в одну строку, а не импорт из `app/worker.py`: `core` не вправе зависеть от
    точки входа процесса. Расхождение номера базы между api и worker'ом было бы молчаливым
    (api ставит в базу 3, worker слушает 0), поэтому обе стороны читают один `REDIS_URL`,
    а не два разных ключа конфигурации.
    """
    return RedisSettings.from_dsn((settings or get_settings()).redis_url.get_secret_value())


async def get_queue() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(queue_redis_settings())
    return _pool


async def close_queue() -> None:
    """Закрывает пул и сбрасывает синглтон — следующий `get_queue()` перечитает конфиг."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
    _pool = None


async def enqueue(function: str, *args: Any) -> str | None:
    """Ставит задачу; возвращает `job_id` или `None`, если поставить не удалось.

    Имя задачи приходит константой от вызывающего (`app.worker.REFRESH_DAILY_STATS_NAME`),
    а не строкой: опечатка иначе обнаружилась бы только тем, что worker молча отвечает
    «нет такой функции» уже после ответа клиенту.
    """
    try:
        job = await (await get_queue()).enqueue_job(function, *args)
    except Exception as error:
        # Текст исключения redis-py может нести URL с паролем — берём только тип.
        log.error("queue.enqueue_failed", function=function, error_type=type(error).__name__)
        return None
    if job is None:
        # arq возвращает None, когда задача с таким `job_id` уже в очереди. Своих
        # `job_id` мы не задаём, поэтому сюда попасть нечем — но None в типе есть.
        log.warning("queue.enqueue_skipped", function=function)
        return None
    return job.job_id
