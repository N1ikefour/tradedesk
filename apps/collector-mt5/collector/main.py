"""Менеджер процессов коллектора — `SPEC.md` §8.2, пункт 1.

Запуск:

    python -m collector.main

Раз в `HEARTBEAT_INTERVAL_SECONDS` менеджер спрашивает `GET /internal/collector/assignments`,
поднимает процесс на каждый новый счёт, гасит процессы исчезнувших (пауза, архив) и шлёт
heartbeat за всех — включая те счета, у которых живого процесса нет и рассказать о себе
поэтому некому.

**Процесс, а не поток.** Библиотека `MetaTrader5` держит одно соединение на процесс, и это
требование библиотеки, а не оптимизация: два счёта в одном процессе означали бы, что
второй `initialize` отбирает соединение у первого.

**Контекст `spawn` задаётся явно.** На Windows другого и нет, а на машине разработки по
умолчанию тоже `spawn` — но полагаться на умолчание нельзя: дочерний процесс не наследует
от родителя ничего, и весь `main.py` устроен исходя из этого. Явный контекст означает, что
тесты на macOS проверяют ту же семантику, что поедет на Windows.

**Пароль счёта через границу процессов не передаётся.** Ребёнок получает только
идентификатор счёта и путь к `collector.env`; пароль он берёт сам, своим запросом
assignments (`CLAUDE.md` §5). Передай его аргументом — и он оказался бы и в pickle-буфере
спавна, и в списке процессов Windows.

Решения «кому дать место» и «перезапускать ли упавшего» живут в `pool.py` чистыми
функциями. Здесь — только процессы, часы и сеть.
"""

from __future__ import annotations

import argparse
import contextlib
import multiprocessing
import signal
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Final, Protocol

from collector import messages, pool, worker
from collector.api_client import ApiClient, ApiError, Assignment, HeartbeatAccount
from collector.config import (
    DEFAULT_ENV_FILENAME,
    CollectorSettings,
    ConfigError,
    load_settings,
    non_ascii_path_warning,
    platform_refusal,
)
from collector.logging_setup import MANAGER_LOG_NAME, get_logger, setup_logging
from collector.worker import (
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_PLATFORM,
    STATE_ERROR,
    STATE_RUNNING,
    STATE_STOPPED,
)

log = get_logger(__name__)

# Менеджер упал сам. Отдельно от кодов процесса счёта: там 2 и 3 означают «эта машина
# никогда не заработает», а здесь — «поднимите коллектор заново».
EXIT_FAILURE: Final = 1

SPAWN: Final = "spawn"

# Сколько ждать, пока убитый процесс действительно умрёт, прежде чем добивать.
STOP_TIMEOUT_SECONDS: Final = 10.0

# Ожидание между тиками режется на куски, чтобы Ctrl+C и SIGTERM не ждали целую минуту.
NAP_SLICE_SECONDS: Final = 1.0

# Что человек прочтёт про счёт, у которого нет живого процесса. Ключ — `pool.Health.status`,
# и таблица обязана покрывать его целиком: пропущенное значение — это счёт, о котором
# менеджер промолчал не по решению, а по недосмотру (закреплено тестом на `get_args`).
#
# `None` — «сказать нечего, и это правильный ответ»: на карточке уже стоит причина точнее
# нашей. Такой счёт получает `state=running` (см. `_member_report`).
HEALTH_REPORTS: Final[dict[pool.MemberStatus, str | None]] = {
    "running": None,
    "explained": None,
    "not_started": messages.WORKER_NOT_STARTED,
    "restarting": messages.WORKER_RESTARTING,
    "exhausted": messages.WORKER_GAVE_UP,
    "fatal": messages.WORKER_FATAL,
}

Sleep = Callable[[float], None]
Monotonic = Callable[[], float]


class ManagerApi(Protocol):
    """То, что менеджер берёт у API. `ApiClient` подходит под него структурно.

    Батча здесь нет намеренно: сделки отправляет процесс счёта, менеджер их не видит.
    """

    def assignments(self, collector_id: str) -> list[Assignment]: ...

    def heartbeat(self, collector_id: str, accounts: Iterable[HeartbeatAccount]) -> None: ...


class Child(Protocol):
    """Дочерний процесс. `multiprocessing.Process` подходит структурно.

    Протокол, а не сам `Process`: настоящий процесс в тестах — это секунды на запуск и
    невозможность подстроить код выхода, а проверять надо именно реакцию менеджера.
    Настоящий `spawn` при этом проверяется отдельно (`tests/test_main.py`) — там, где
    важен он сам, а не решения вокруг него.
    """

    @property
    def pid(self) -> int | None: ...

    @property
    def exitcode(self) -> int | None: ...

    def is_alive(self) -> bool: ...

    def join(self, timeout: float | None = None) -> None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


SpawnChild = Callable[[str], Child]


def _exit_code_text(code: int | None) -> str:
    """Код выхода в текст для человека. `None` — процесса не было или код не сообщён."""
    return "неизвестен" if code is None else str(code)


@dataclass
class Member:
    """Счёт, за которым закреплено место в пуле.

    Место остаётся за счётом и пока его процесс мёртв: `pool.plan_slots` считает
    занятыми все места, а не только живые.
    """

    account_id: str
    child: Child | None = None
    started_at: float = 0.0
    health: pool.Health = pool.HEALTHY


# --------------------------------------------------------------------------------------
# Дочерний процесс
# --------------------------------------------------------------------------------------


def run_account(account_id: str, env_file: str) -> None:
    """Точка входа дочернего процесса. При `spawn` он не наследует ничего.

    Ни настроек, ни поднятого логирования, ни — что важнее всего — реестра секретов
    скраба (`logging_setup`). Поэтому здесь зовётся `worker.main`, то есть **полный**
    старт процесса счёта: он сам читает `collector.env`, сам поднимает лог со скрабом
    токена и сам получает пароль счёта из assignments, а `Assignment.__post_init__`
    вносит пароль в скраб уже этого процесса.

    Иными словами, инвариант «пароля нет в логах» (`CLAUDE.md` §5) в ребёнке держится не
    на наследовании, которого нет, а на том, что ребёнок проходит тот же старт, что и
    ручной запуск `python -m collector.worker`.
    """
    raise SystemExit(worker.main(["--account-id", account_id, "--env-file", env_file]))


def spawn_worker(account_id: str, env_file: Path) -> Child:
    """Поднять процесс счёта. Единственное место, где менеджер трогает `multiprocessing`."""
    context = multiprocessing.get_context(SPAWN)
    process = context.Process(
        target=run_account,
        args=(account_id, str(env_file)),
        name=f"collector-{account_id}",
        # Демон гасит детей при **штатном** выходе менеджера — через `atexit`, и только
        # так. Жёсткое завершение (`taskkill /F`, «Снять задачу», `kill -9`) `atexit` не
        # выполняет, и дети переживают родителя: сироты — открытое допущение 39 в
        # `docs/mt5-assumptions.md`, а не закрытый этим флагом вопрос. Ограничение демонов
        # (нельзя иметь своих детей) коллектора не задевает: терминал поднимает не
        # `multiprocessing`, а сама библиотека MT5.
        daemon=True,
    )
    process.start()
    return process


# --------------------------------------------------------------------------------------
# Менеджер
# --------------------------------------------------------------------------------------


@dataclass
class Manager:
    """Пул процессов по счетам. Процессы и сеть приходят снаружи — иначе это не проверить."""

    settings: CollectorSettings
    api: ManagerApi
    spawn: SpawnChild
    sleep: Sleep = time.sleep
    monotonic: Monotonic = time.monotonic
    max_restarts: int = pool.MAX_RESTARTS
    _members: dict[str, Member] = field(default_factory=dict, init=False)
    _over_limit: tuple[str, ...] = field(default=(), init=False)
    _stopping: bool = field(default=False, init=False)
    # Список счетов не пришёл на последнем тике: состав пула и перезапуски заморожены.
    _frozen: bool = field(default=False, init=False)
    # Чем закончился цикл, если исключением. Прощальный heartbeat зависит от этого.
    _crash: str | None = field(default=None, init=False)

    def run(self, *, max_ticks: int = 0) -> int:
        """Крутить пул. `max_ticks=0` — бесконечно, как в бою; число — столько тиков."""
        log.info(
            "collector.manager_started",
            collector_id=self.settings.collector_id,
            max_accounts=self.settings.max_accounts,
            interval=self.settings.heartbeat_interval_seconds,
        )
        ticks = 0
        try:
            while not self._stopping:
                self._tick()
                ticks += 1
                if max_ticks and ticks >= max_ticks:
                    break
                self._nap()
        except Exception as error:
            # Единственный случай, когда о счёте некому рассказать буквально: менеджер
            # умирает вместе со своими процессами, а `print` под Task Scheduler уходит в
            # никуда. Прощальный heartbeat отсюда — единственное, что доедет до карточки.
            self._crash = messages.MANAGER_CRASHED.format(error=type(error).__name__)
            raise
        finally:
            self._shutdown()
        return EXIT_OK

    def stop(self) -> None:
        """Попросить менеджер остановиться. Зовётся из обработчика сигнала."""
        self._stopping = True

    # -- один тик --------------------------------------------------------------------

    def _tick(self) -> None:
        self._reap()
        assignments = self._assignments()
        self._frozen = assignments is None
        if assignments is not None:
            self._apply(assignments)
        self._report()

    def _assignments(self) -> list[str] | None:
        """Счета этого коллектора. `None` — API молчит, состав пула не трогаем.

        Молчание API не имеет права гасить процессы: одна неудачная минута иначе снимала
        бы все терминалы, а следующая поднимала бы их заново — с полной перезагрузкой
        истории и без единой сделки за это время.

        **Вместе с составом замирают и перезапуски**, потому что `_ensure_running` зовётся
        из `_apply`. Это решение, а не побочный эффект (`SPEC.md` §8.2): процесс счёта без
        связи с API умирает сразу — задание с паролем берётся оттуда же, — и поднимать его
        в этот момент значит сжечь все пять попыток за пять минут, а потом оставить счёт
        лежать до перезапуска коллектора руками. Пока связи нет, счёт с мёртвым процессом
        читает `messages.WORKER_RESTART_DEFERRED`, а не обещание немедленного перезапуска.
        """
        try:
            return [item.account_id for item in self.api.assignments(self.settings.collector_id)]
        except ApiError as error:
            log.warning("collector.assignments_unavailable", reason=error.message)
            return None

    def _apply(self, assigned: Sequence[str]) -> None:
        plan = pool.plan_slots(
            held=tuple(self._members),
            assigned=assigned,
            limit=self.settings.max_accounts,
        )
        for account_id in plan.release:
            self._stop_member(account_id, reason="unassigned")
        for account_id in plan.take:
            self._members[account_id] = Member(account_id=account_id)
        if plan.over_limit != self._over_limit:
            # Одной строкой на изменение состава, а не на каждый тик: счёт сверх лимита —
            # состояние, которое держится сутками, и минутная строка о нём вытеснила бы
            # из `collector.log` всё остальное ещё до того, как человек туда заглянет.
            log.error(
                "collector.accounts_over_limit",
                account_ids=list(plan.over_limit),
                max_accounts=self.settings.max_accounts,
            )
        self._over_limit = plan.over_limit
        for member in self._members.values():
            self._ensure_running(member)

    def _reap(self) -> None:
        """Собрать умерших. Процесс вправе умереть и снаружи цикла — OOM, убит системой."""
        for member in self._members.values():
            child = member.child
            if child is None or child.is_alive():
                continue
            # `exitcode` у мёртвого процесса не `None`, но если гонка оставила его пустым —
            # это падение с неизвестным кодом, и человек прочтёт именно это. Подставить
            # сюда `EXIT_ACCOUNT` значило бы соврать, что процесс успел назвать причину сам.
            code = child.exitcode
            lived = self.monotonic() - member.started_at
            member.child = None
            member.health = pool.after_exit(
                member.health,
                exit_code=code,
                lived_seconds=lived,
                now=self.monotonic(),
                max_restarts=self.max_restarts,
            )
            log.error(
                "collector.worker_died",
                account_id=member.account_id,
                exit_code=code,
                lived_seconds=round(lived, 1),
                failures=member.health.failures,
                status=member.health.status,
            )

    def _ensure_running(self, member: Member) -> None:
        if member.child is not None:
            return
        if not pool.may_start(member.health, now=self.monotonic()):
            return
        try:
            member.child = self.spawn(member.account_id)
        except OSError as error:
            # Не хватило памяти или дескрипторов. Считается падением, а не поводом уронить
            # менеджер: остальные счета продолжают синхронизироваться.
            log.error(
                "collector.worker_not_started",
                account_id=member.account_id,
                reason=type(error).__name__,
            )
            member.health = pool.after_failed_start(
                member.health,
                now=self.monotonic(),
                max_restarts=self.max_restarts,
            )
            return
        member.started_at = self.monotonic()
        log.info(
            "collector.worker_started",
            account_id=member.account_id,
            pid=member.child.pid,
            attempt=member.health.failures + 1,
        )

    def _stop_member(self, account_id: str, *, reason: str) -> None:
        """Погасить процесс счёта: пауза, архив или счёт ушёл к другому коллектору.

        Недоотправленный батч при этом теряется, и это осознанная цена. Потери данных нет:
        сервер двигает `last_sync_at` только на принятом батче, окно следующего запуска
        начинается от него минус сутки, а вставка идемпотентна (`SPEC.md` §5.3). Из
        нескольких частей окна уже принятые остаются принятыми — каждая едет своей
        транзакцией.
        """
        member = self._members.pop(account_id, None)
        if member is None or member.child is None:
            return
        child = member.child
        if not child.is_alive():
            return
        log.info("collector.worker_stopping", account_id=account_id, pid=child.pid, reason=reason)
        child.terminate()
        child.join(STOP_TIMEOUT_SECONDS)
        if child.is_alive():
            # Терминал мог зависнуть в нативном вызове, и `terminate` его не разбудит.
            child.kill()
            child.join(STOP_TIMEOUT_SECONDS)
            log.warning("collector.worker_killed", account_id=account_id, pid=child.pid)

    # -- отчёт человеку ---------------------------------------------------------------

    def _report(self) -> None:
        """Периодический heartbeat за все счета сразу — `SPEC.md` §8.2, пункт 1.

        Менеджер шлёт его **за всех**, потому что он единственный, кто может рассказать о
        счёте без живого процесса: сверх лимита, упал, перезапуски кончились. Процесс
        счёта продолжает слать свой heartbeat по смене состояния (`S1-08`), и они не
        спорят: `state=running` от менеджера обновляет только `last_heartbeat_at`, а
        статус и текст причины ставит `state=error` — чей угодно (`accounts.service`).
        """
        accounts = [self._member_report(member) for member in self._members.values()]
        accounts.extend(
            HeartbeatAccount(
                account_id=account_id,
                state=STATE_ERROR,
                message=messages.over_limit(self.settings.max_accounts),
            )
            for account_id in self._over_limit
        )
        self._send(accounts)

    def _member_report(self, member: Member) -> HeartbeatAccount:
        """Что менеджер скажет про один счёт. Молчание здесь — полноценный ответ.

        **`state=running` от менеджера значит «коллектор ведёт этот счёт», а не «процесс
        сейчас жив»** (`SPEC.md` §8.2). Живому процессу оно достаётся без сообщения: `state`
        в контракте — состояние процесса (`SPEC.md` §5.3), и менеджер не имеет права
        переписать причину, которую поставил сам счёт. То же самое достаётся мёртвому
        процессу, ушедшему с `EXIT_ACCOUNT`: он причину уже назвал — «счёт не в USD»,
        «батч отвергнут», — и общий текст менеджера на её месте отправил бы человека
        собирать логи вместо того, чтобы прочитать диагноз. `running` в этом случае нужен
        не как утверждение о процессе, а чтобы `last_heartbeat_at` двигался и
        `check_collectors` (`SPEC.md` §10) через пять минут не заменил точную причину на
        «коллектор не на связи».

        Живость берётся из последнего `_reap`, а не из свежего `is_alive()`. Иначе отчёт
        собирался бы из двух источников с разным возрастом: смерть свежая, а причина —
        от прошлого падения, и на карточку уходило бы «процесс завершился (код -9)» про
        процесс, поднятый минуту назад. Смерть разбирается следующим тиком, целиком.
        """
        status: pool.MemberStatus = "running" if member.child is not None else member.health.status
        template = self._report_template(status)
        if template is None:
            return HeartbeatAccount(account_id=member.account_id, state=STATE_RUNNING)
        return HeartbeatAccount(
            account_id=member.account_id,
            state=STATE_ERROR,
            message=messages.fit(
                template.format(
                    code=_exit_code_text(member.health.last_exit_code),
                    attempts=member.health.failures,
                )
            ),
        )

    def _report_template(self, status: pool.MemberStatus) -> str | None:
        if status == "restarting" and self._frozen:
            return messages.WORKER_RESTART_DEFERRED
        return HEALTH_REPORTS[status]

    def _send(self, accounts: Sequence[HeartbeatAccount]) -> None:
        if not accounts:
            return
        try:
            self.api.heartbeat(self.settings.collector_id, accounts)
        except ApiError as error:
            # Heartbeat, который не доехал, не имеет права остановить пул: процессы живут
            # своей жизнью и шлют сделки, а отметка о состоянии повторится через минуту.
            log.warning("collector.heartbeat_failed", reason=error.message)

    # -- служебное ---------------------------------------------------------------------

    def _nap(self) -> None:
        """Пауза между тиками, порезанная на куски: сигнал не должен ждать целую минуту."""
        remaining = float(self.settings.heartbeat_interval_seconds)
        while remaining > 0 and not self._stopping:
            nap = min(NAP_SLICE_SECONDS, remaining)
            self.sleep(nap)
            remaining -= nap

    def _shutdown(self) -> None:
        """Погасить всё и сказать об этом. Зовётся и при штатном выходе, и при исключении.

        Штатная остановка — `state=stopped`: она статуса не меняет (`accounts.service`),
        и это верно, потому что коллектор остановил человек. Крах — `state=error` с текстом
        `MANAGER_CRASHED`: иначе о нём не узнал бы никто, кроме файла лога, а на карточке
        через пять минут появилось бы «коллектор не на связи» вместо причины.

        Счета сверх лимита прощального сообщения не получают ни в том, ни в другом случае:
        на их карточках уже стоит своя причина, и она остаётся верной — синхронизации у
        них не было и до остановки.
        """
        account_ids = list(self._members)
        for account_id in account_ids:
            self._stop_member(account_id, reason="shutdown")
        self._over_limit = ()
        state = STATE_ERROR if self._crash is not None else STATE_STOPPED
        message = self._crash if self._crash is not None else messages.STOPPED
        self._send(
            [
                HeartbeatAccount(account_id=account_id, state=state, message=message)
                for account_id in account_ids
            ]
        )
        log.info("collector.manager_stopped", accounts=len(account_ids), crashed=bool(self._crash))


# --------------------------------------------------------------------------------------
# Точка входа
# --------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collector.main",
        description="Менеджер процессов коллектора MT5: счёт — процесс",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(DEFAULT_ENV_FILENAME),
        help=f"Путь к файлу настроек (по умолчанию {DEFAULT_ENV_FILENAME})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Один тик и выход: спросить assignments, поднять процессы счетов и тут же "
            "погасить их. Проверка связи и настроек, а не синхронизация"
        ),
    )
    return parser


def install_signal_handlers(manager: Manager) -> None:
    """Ctrl+C и `SIGTERM` гасят пул по-человечески: цикл доходит до `_shutdown`.

    ⚠️ На Windows настоящий сигнал доходит только от консоли (`SIGINT`, `SIGBREAK`).
    `taskkill /F` и «Снять задачу» — то есть обычный способ остановки под Task Scheduler —
    это `TerminateProcess`: ни обработчика, ни `atexit`, ни `finally`. Процессы счетов
    после такого остаются жить со своим токеном и своим циклом (`docs/mt5-assumptions.md`,
    допущение 39), и следующий старт поднимет для тех же счетов вторые.
    """

    def handler(signal_number: int, _frame: FrameType | None) -> None:
        log.info("collector.manager_signal", signal=signal_number)
        manager.stop()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        number = getattr(signal, name, None)
        if number is None:
            continue
        with contextlib.suppress(ValueError, OSError):
            signal.signal(number, handler)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    refusal = platform_refusal()
    if refusal is not None:
        print(refusal)
        return EXIT_PLATFORM

    try:
        settings = load_settings(args.env_file)
    except ConfigError as error:
        print(str(error))
        return EXIT_CONFIG

    setup_logging(
        log_file=settings.log_dir / MANAGER_LOG_NAME,
        level=settings.log_level,
        secrets=settings.secrets,
    )
    for path in (settings.mt5_terminal_exe, settings.mt5_portable_root):
        warning = non_ascii_path_warning(path)
        if warning is not None:
            log.warning("collector.non_ascii_path", message=warning)

    env_file = args.env_file.resolve()
    with ApiClient(settings) as api:
        manager = Manager(
            settings=settings,
            api=api,
            spawn=lambda account_id: spawn_worker(account_id, env_file),
        )
        install_signal_handlers(manager)
        try:
            return manager.run(max_ticks=1 if args.once else 0)
        except KeyboardInterrupt:
            log.info("collector.manager_interrupted")
            return EXIT_OK
        except Exception as error:
            # Тот же рубеж, что у процесса счёта, и по той же причине: под Task Scheduler
            # (`S1-10`) консоли нет, и трейсбек из `sys.excepthook` не попал бы никуда.
            log.exception("collector.manager_crashed")
            print(messages.MANAGER_CRASHED.format(error=type(error).__name__))
            return EXIT_FAILURE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
