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

`refresh_daily_stats` (§10) зарегистрирована как задача **по вызову**, а не по расписанию:
`daily_stats` — кэш, который никто пока не читает (`docs/metrics.md` §6), и гонять его по
кругу незачем. Ставит её в очередь тот, кто изменил сделки, — `POST /ingest/deals` (`S1-04`)
и ручные сделки (`S2-03`); ни того, ни другого ещё нет, поэтому сегодня очередь наполняют
только тесты.

`cleanup_otp()` из §10 здесь не зарегистрирован: функции в коде нет (просроченный код
входа не пускает по проверке `expires_at`, см. `domains/auth/service.py`). Появится
вместе со своей задачей — писать домен в инфраструктурной обёртке не место.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings
from arq.cron import CronJob
from arq.worker import run_worker

from app.core.config import Settings, get_settings
from app.core.db import dispose_engine, get_session_factory
from app.core.logging import configure_logging, get_logger
from app.core.security import master_key_scrub_values
from app.domains.accounts import service as accounts_service
from app.domains.analytics import daily_stats

log = get_logger(__name__)

CHECK_COLLECTORS_NAME = "check_collectors"
REFRESH_DAILY_STATS_NAME = "refresh_daily_stats"


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


async def refresh_daily_stats(
    ctx: dict[str, Any], account_id: str, days: list[str] | None = None
) -> int:
    """Пересчитывает суточную агрегацию счёта (SPEC.md §10).

    Аргументы примитивные (строки, а не `UUID` и `date`) намеренно: их сериализует
    очередь, и через неё они переживают перезапуск worker'а вместе с версией кода,
    которая их положила. Разбор — здесь, на входе задачи; домен получает уже типы.
    """
    parsed = None if days is None else [date.fromisoformat(day) for day in days]
    async with get_session_factory()() as session:
        written = await daily_stats.refresh(session, UUID(account_id), parsed)
    log.info("worker.daily_stats_refreshed", account_id=account_id, days=written)
    return written


# Задачи по вызову: в очередь их ставит api, расписания у них нет.
FUNCTIONS: list[Any] = [refresh_daily_stats]


def worker_redis_settings(settings: Settings | None = None) -> RedisSettings:
    return RedisSettings.from_dsn((settings or get_settings()).redis_url.get_secret_value())


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await dispose_engine()


def worker_settings() -> dict[str, Any]:
    """Аргументы `arq.worker.Worker`. Словарь, а не класс с атрибутами: arq принимает обе
    формы, но класс читает `REDIS_URL` в момент импорта модуля, а не запуска процесса.
    """
    return {
        "functions": FUNCTIONS,
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
        functions=[function.__name__ for function in FUNCTIONS],
        secrets=settings.secret_presence(),
    )
    run_worker(worker_settings())


if __name__ == "__main__":
    main()
