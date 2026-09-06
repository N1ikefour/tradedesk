"""Планировщик фоновых задач (arq) — SPEC.md §10.

Здесь только запуск. Что считать «коллектор замолчал» и что с этим делать, решает
`accounts.service.check_collectors` (S1-05); обёртка ниже открывает сессию и зовёт домен.

**Недоступный Redis — громкий отказ, а не тихое ожидание.** Проверено остановкой redis
на живом стеке. Пропавший redis роняет процесс с трассировкой и ненулевым кодом, docker
поднимает его заново (`restart: unless-stopped`), и на старте `arq.create_pool` делает
`conn_retries` попыток с паузой `conn_retry_delay` — то есть переживает разрыв длиной
в несколько секунд, но не переживает выключенный redis. Пока redis не вернётся, контейнер
остаётся в цикле рестартов, и это видно в `docker ps`. Вечное ожидание внутри процесса
было бы хуже: контейнер числился бы живым, а задачи не шли бы — ровно тот молчаливый
отказ, который эта задача и должна ловить. `make up` от этого не страдает: worker не
стартует раньше, чем redis пройдёт healthcheck, поэтому в цикл рестартов на старте
он не попадает.

**Два worker'а — один прогон.** `cron(..., unique=True)` даёт задаче job_id вида
`<имя>:<время следующего запуска>`, и второй worker на ту же минуту получает от Redis
отказ по занятому ключу. Для `check_collectors` это некритично — UPDATE идемпотентен, —
но `send_email` и `export_user_data` из того же §10 идемпотентными не будут, и правило
должно действовать до их появления, а не после первого продублированного письма.
`unique=False` в этом модуле запрещён, проверяет `tests/unit/test_worker.py`.

`cleanup_otp()` из §10 здесь не зарегистрирован: функции в коде нет (просроченный код
входа не пускает по проверке `expires_at`, см. `domains/auth/service.py`). Появится
вместе со своей задачей — писать домен в инфраструктурной обёртке не место.
"""

from __future__ import annotations

from typing import Any

from arq import cron
from arq.connections import RedisSettings
from arq.cron import CronJob
from arq.worker import run_worker

from app.core.config import Settings, get_settings
from app.core.db import dispose_engine, get_session_factory
from app.core.logging import configure_logging, get_logger
from app.core.security import master_key_scrub_values
from app.domains.accounts import service as accounts_service

log = get_logger(__name__)

CHECK_COLLECTORS_NAME = "check_collectors"


async def check_collectors(ctx: dict[str, Any]) -> int:
    """Уводит счета с замолчавшим коллектором в `needs_attention` (SPEC.md §10)."""
    async with get_session_factory()() as session:
        offline = await accounts_service.check_collectors(session)
    if offline:
        # Идентификаторы счетов — не секрет, и без них по логу не понять, какой именно
        # счёт отвалился. Пустой прогон не логируется: это 1440 строк в сутки ни о чём.
        log.info("worker.collectors_offline", accounts=[str(account) for account in offline])
    return len(offline)


# `second=0` без указания минут — начало каждой минуты (SPEC.md §10).
# `run_at_startup` намеренно выключен: следующий тик не дальше минуты, а на старте worker
# обогнал бы `alembic upgrade head`, который катит api, и первый же прогон падал бы на
# отсутствующей таблице при развёртывании на чистом томе.
CRON_JOBS: list[CronJob] = [
    cron(check_collectors, name=CHECK_COLLECTORS_NAME, second=0, unique=True),
]


def worker_redis_settings(settings: Settings | None = None) -> RedisSettings:
    return RedisSettings.from_dsn((settings or get_settings()).redis_url.get_secret_value())


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await dispose_engine()


def worker_settings() -> dict[str, Any]:
    """Аргументы `arq.worker.Worker`. Словарь, а не класс с атрибутами: arq принимает обе
    формы, но класс читает `REDIS_URL` в момент импорта модуля, а не запуска процесса.

    `functions` (задачи по вызову из SPEC.md §10) здесь нет: очередь пока никто не
    наполняет, а Worker и без них не пуст — cron_jobs попадают в тот же реестр.
    """
    return {
        "cron_jobs": CRON_JOBS,
        "redis_settings": worker_redis_settings(),
        "on_shutdown": on_shutdown,
    }


def main() -> None:
    """Точка входа контейнера `worker`.

    Своя, а не штатный CLI `arq`: тот зовёт `logging.config.dictConfig` и сносит
    конфигурацию structlog. Логи worker'а перестали бы быть тем же JSON, что у api,
    и вместе с конфигурацией ушёл бы скраб секретов из текста исключений.
    """
    settings = get_settings()
    configure_logging(
        secret_values=[*settings.scrubbable_secret_values(), *master_key_scrub_values(settings)]
    )
    log.info(
        "worker.starting",
        app_env=settings.app_env,
        cron_jobs=[job.name for job in CRON_JOBS],
        secrets=settings.secret_presence(),
    )
    run_worker(worker_settings())


if __name__ == "__main__":
    main()
