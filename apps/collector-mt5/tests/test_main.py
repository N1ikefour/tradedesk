"""Менеджер процессов на подделках — `SPEC.md` §8.2, пункт 1.

Настоящих процессов здесь два вида, и разделены они намеренно.

Пул проверяется на подделках: настоящий процесс — это секунды на запуск, невозможность
задать код выхода и невозможность вообще запустить `worker.py` на macOS. Проверяется
поэтому реакция менеджера, а не `multiprocessing`.

`spawn` проверяется настоящим процессом — там, где важен именно он: дочерний процесс не
наследует от родителя **ничего**, и реестр секретов скраба логов (`CLAUDE.md` §5) в нём
приходится поднимать заново. Это тот случай, где инвариант разваливается тихо, поэтому
он измеряется, а не предполагается.
"""

from __future__ import annotations

import multiprocessing
import multiprocessing.queues
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_args

import pytest

from collector import logging_setup, messages, pool
from collector import main as manager_module
from collector.api_client import ApiError, Assignment, HeartbeatAccount
from collector.config import CollectorSettings
from collector.main import EXIT_FAILURE, Child, Manager
from collector.worker import (
    EXIT_ACCOUNT,
    EXIT_CONFIG,
    EXIT_PLATFORM,
    STATE_ERROR,
    STATE_RUNNING,
    STATE_STOPPED,
)
from tests.conftest import COLLECTOR_ID, TOKEN

A, B, C, D = "acc-a", "acc-b", "acc-c", "acc-d"

# Смерть, о которой процесс счёта рассказать не успел: убит системой, OOM, `taskkill /F`.
# Только о такой менеджеру и есть что сказать — код `EXIT_ACCOUNT` означает обратное.
CRASH = -9

CHILD_ACCOUNT = "0192f1d4-2c6a-7c3f-9d1e-2b6a8f4c1d55"
CHILD_PASSWORD = "investor-password-42"


# --------------------------------------------------------------------------------------
# Подделки
# --------------------------------------------------------------------------------------


@dataclass
class FakeChild:
    """Дочерний процесс, который делает ровно то, что ему сказали в тесте."""

    account_id: str
    alive: bool = True
    exitcode: int | None = None
    pid: int | None = 4242
    terminated: int = 0
    killed: int = 0
    # Процесс, зависший в нативном вызове терминала: `terminate` его не разбудит.
    ignores_terminate: bool = False

    def is_alive(self) -> bool:
        return self.alive

    def join(self, timeout: float | None = None) -> None:
        return None

    def terminate(self) -> None:
        self.terminated += 1
        if not self.ignores_terminate:
            self.alive = False
            self.exitcode = -15

    def kill(self) -> None:
        self.killed += 1
        self.alive = False
        self.exitcode = -9

    def die(self, code: int) -> None:
        """Процесс умер сам: упал, съел память, убит системой."""
        self.alive = False
        self.exitcode = code


@dataclass
class FakeSpawn:
    """Фабрика процессов. Помнит всех, кого когда-либо поднимали."""

    children: list[FakeChild] = field(default_factory=list)
    fail: Exception | None = None
    stubborn: bool = False

    def __call__(self, account_id: str) -> Child:
        if self.fail is not None:
            raise self.fail
        child = FakeChild(account_id=account_id, ignores_terminate=self.stubborn)
        self.children.append(child)
        return child

    def kill_all(self, code: int = EXIT_ACCOUNT) -> None:
        for child in self.children:
            child.die(code)

    def of(self, account_id: str) -> list[FakeChild]:
        return [child for child in self.children if child.account_id == account_id]


@dataclass
class FakeManagerApi:
    """API без сети: список счетов и журнал того, что менеджер о них сказал."""

    accounts: list[str] = field(default_factory=list)
    assignments_error: ApiError | None = None
    # Не `ApiError`: так проверяется падение самого менеджера, а не недоступность API.
    assignments_crash: Exception | None = None
    # Что случается в мире ПОСЛЕ `_reap` и ДО `_report` этого же тика.
    on_assignments: Callable[[], None] | None = None
    heartbeat_error: ApiError | None = None
    heartbeats: list[list[HeartbeatAccount]] = field(default_factory=list)
    asked: int = 0

    def assignments(self, collector_id: str) -> list[Assignment]:
        self.asked += 1
        if self.on_assignments is not None:
            self.on_assignments()
        if self.assignments_crash is not None:
            raise self.assignments_crash
        if self.assignments_error is not None:
            raise self.assignments_error
        return [
            Assignment(
                account_id=account_id,
                server="E-Global-Real",
                login=1234567,
                password="investor-secret",
                sync_requested_at=None,
                last_sync_at=None,
                status="pending",
            )
            for account_id in self.accounts
        ]

    def heartbeat(self, collector_id: str, accounts: Iterable[HeartbeatAccount]) -> None:
        if self.heartbeat_error is not None:
            raise self.heartbeat_error
        self.heartbeats.append(list(accounts))

    def report(self, index: int = -1) -> dict[str, HeartbeatAccount]:
        """Один отчёт по счетам. `-1` — прощальный (`stopped`), `-2` — последний рабочий."""
        return {account.account_id: account for account in self.heartbeats[index]}


class Clock:
    """Монотонные часы, которыми управляет тест."""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _manager(
    settings: CollectorSettings,
    api: FakeManagerApi,
    spawn: FakeSpawn,
    *,
    between_ticks: Callable[[], None] | None = None,
    max_restarts: int = pool.MAX_RESTARTS,
) -> tuple[Manager, Clock]:
    """Менеджер с подделками. `between_ticks` — что случилось в мире, пока он спал.

    Ожидание двигает часы: иначе паузы перед перезапуском не проходили бы никогда, и тест
    проверял бы не политику перезапуска, а её отсутствие. Обратный вызов приходится на
    каждый кусок сна, поэтому обязан быть идемпотентным.
    """
    clock = Clock()

    def sleep(seconds: float) -> None:
        clock.value += seconds
        if between_ticks is not None:
            between_ticks()

    manager = Manager(
        settings=settings,
        api=api,
        spawn=spawn,
        sleep=sleep,
        monotonic=clock,
        max_restarts=max_restarts,
    )
    return manager, clock


# --------------------------------------------------------------------------------------
# Пул: кого подняли, кого погасили
# --------------------------------------------------------------------------------------


def test_two_accounts_run_at_once(settings: CollectorSettings) -> None:
    """DoD `S1-09`: два счёта одновременно — два процесса, по одному на счёт."""
    api = FakeManagerApi(accounts=[A, B])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn)

    manager.run(max_ticks=1)

    assert [child.account_id for child in spawn.children] == [A, B]


def test_pausing_an_account_stops_its_process_only(settings: CollectorSettings) -> None:
    """DoD `S1-09`: пауза одного счёта останавливает его процесс, второй продолжает.

    Пауза и архив приходят одинаково — счёт просто исчезает из assignments (`SPEC.md` §5.6).
    """
    api = FakeManagerApi(accounts=[A, B])
    spawn = FakeSpawn()

    def pause_b() -> None:
        api.accounts = [A]

    manager, _ = _manager(settings, api, spawn, between_ticks=pause_b)

    manager.run(max_ticks=2)

    paused = spawn.of(B)[0]
    assert paused.terminated == 1
    assert not paused.alive
    assert spawn.of(A)[0].terminated == 1  # погашен только на выходе из цикла
    assert len(spawn.of(A)) == 1


def test_a_process_is_started_once_and_left_alone(settings: CollectorSettings) -> None:
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn)

    manager.run(max_ticks=3)

    assert len(spawn.children) == 1


def test_api_silence_does_not_touch_the_pool(settings: CollectorSettings) -> None:
    """Одна неудачная минута не имеет права снять все терминалы."""
    api = FakeManagerApi(accounts=[A, B])
    spawn = FakeSpawn()

    def blind() -> None:
        api.assignments_error = ApiError("TradeDesk не отвечает")

    manager, _ = _manager(settings, api, spawn, between_ticks=blind)

    manager.run(max_ticks=3)

    assert len(spawn.children) == 2
    assert all(child.terminated == 1 for child in spawn.children)  # только на выходе


# --------------------------------------------------------------------------------------
# Лимит
# --------------------------------------------------------------------------------------


def test_account_over_the_limit_is_visible_to_the_human(settings: CollectorSettings) -> None:
    """⚠️ `SPEC.md` §12 (`S1-09`): счёт сверх `MAX_ACCOUNTS` уходит в `needs_attention`.

    Первому пользователю нужно четыре счёта, а значение по умолчанию — три. Молча
    выпавший из пула счёт не синхронизировался бы никогда, и причину не узнал бы никто.
    """
    api = FakeManagerApi(accounts=[A, B, C, D])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn)

    manager.run(max_ticks=1)

    assert len(spawn.children) == settings.max_accounts
    extra = api.report(0)[D]
    assert extra.state == STATE_ERROR
    assert extra.message is not None
    assert f"MAX_ACCOUNTS={settings.max_accounts}" in extra.message
    assert "collector.env" in extra.message


def test_the_same_account_stays_the_one_over_the_limit(settings: CollectorSettings) -> None:
    """Причина не имеет права каждую минуту переезжать на другой счёт."""
    api = FakeManagerApi(accounts=[A, B, C, D])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn)

    manager.run(max_ticks=3)

    for reported in api.heartbeats[:-1]:  # последний отчёт — прощальный
        over = [item.account_id for item in reported if item.state == STATE_ERROR]
        assert over == [D]


def test_a_freed_slot_goes_to_the_waiting_account(settings: CollectorSettings) -> None:
    api = FakeManagerApi(accounts=[A, B, C, D])
    spawn = FakeSpawn()

    def pause_b() -> None:
        api.accounts = [A, C, D]

    manager, _ = _manager(settings, api, spawn, between_ticks=pause_b)

    manager.run(max_ticks=2)

    assert spawn.of(D)
    assert api.report(-2)[D].state == STATE_RUNNING


# --------------------------------------------------------------------------------------
# Смерть дочернего процесса
# --------------------------------------------------------------------------------------


def test_dead_child_is_restarted_and_the_human_hears_about_it(
    settings: CollectorSettings,
) -> None:
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn, between_ticks=lambda: spawn.children[0].die(-9))

    manager.run(max_ticks=3)

    assert len(spawn.of(A)) == 2
    told = [
        item.message
        for reported in api.heartbeats
        for item in reported
        if item.state == STATE_ERROR
    ]
    assert told and told[0] is not None
    assert "запускает его заново" in told[0]
    assert "-9" in told[0]


def test_a_restart_is_not_immediate(settings: CollectorSettings) -> None:
    """Упавший процесс не поднимается в тот же тик: пауза растёт с каждым падением."""
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn, between_ticks=lambda: spawn.children[0].die(-9))

    manager.run(max_ticks=2)

    assert len(spawn.children) == 1
    assert api.report(-2)[A].state == STATE_ERROR


def test_restarts_run_out_and_the_message_says_so(settings: CollectorSettings) -> None:
    """Перезапуски не бесконечны: кончились — человек получает текст, а не тишину.

    Смерть здесь молчаливая (убит системой): о процессе, ушедшем с кодом 4, менеджеру
    говорить нечего — см. `test_the_reason_named_by_the_worker_survives_the_manager`.
    """
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    manager, _ = _manager(
        settings, api, spawn, between_ticks=lambda: spawn.kill_all(CRASH), max_restarts=2
    )

    manager.run(max_ticks=7)

    assert len(spawn.children) == 1 + 2
    final = api.report(-2)[A]
    assert final.state == STATE_ERROR
    assert final.message is not None
    assert "больше не поднимает" in final.message
    assert "попыток: 3" in final.message


def test_configuration_error_in_the_child_is_never_retried(
    settings: CollectorSettings,
) -> None:
    """Код 2 значит «тот же `collector.env` не заработает» — перезапуск только скроет причину."""
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn, between_ticks=lambda: spawn.kill_all(EXIT_CONFIG))

    manager.run(max_ticks=4)

    assert len(spawn.children) == 1
    final = api.report(-2)[A]
    assert final.message is not None
    assert "Перезапуск не поможет" in final.message


def test_platform_refusal_in_the_child_is_never_retried(settings: CollectorSettings) -> None:
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn, between_ticks=lambda: spawn.kill_all(EXIT_PLATFORM))

    manager.run(max_ticks=4)

    assert len(spawn.children) == 1


def test_a_process_that_cannot_be_started_is_not_a_crash(settings: CollectorSettings) -> None:
    """Не хватило памяти на ещё один терминал — менеджер остаётся жив и говорит об этом.

    Текст здесь свой, а не «пришлите файл лога счёта»: процесса не было, значит и файла
    `account-<id>.log` не существует — человек искал бы то, чего нет.
    """
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn(fail=OSError("cannot allocate memory"))
    manager, _ = _manager(settings, api, spawn)

    assert manager.run(max_ticks=1) == 0
    reported = api.report(0)[A]
    assert reported.state == STATE_ERROR
    assert reported.message is not None
    assert "не смог запустить процесс" in reported.message
    assert "памяти" in reported.message
    assert "LOG_DIR" not in reported.message


# --------------------------------------------------------------------------------------
# Чья причина попадёт на карточку счёта
# --------------------------------------------------------------------------------------


def test_the_reason_named_by_the_worker_survives_the_manager(
    settings: CollectorSettings,
) -> None:
    """⚠️ Менеджер не имеет права перекрыть причину, которую процесс счёта уже назвал.

    Код 4 — это «я сказал человеку, почему ухожу»: `worker.py` перед каждым таким выходом
    шлёт heartbeat `state=error` с точным текстом («Счёт не в USD: валюта счёта EUR…»).
    Общее «пришлите разработчику файл лога» на его месте — обмен диагноза на просьбу
    собирать логи, ровно тот отказ, против которого написан `messages.py`.

    Менеджер при этом не молчит совсем: `state=running` двигает `last_heartbeat_at`, и
    через пять минут `check_collectors` не заменит причину на «коллектор не на связи».
    """
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn, between_ticks=lambda: spawn.kill_all(EXIT_ACCOUNT))

    manager.run(max_ticks=2)

    said = [item for reported in api.heartbeats[:-1] for item in reported]
    assert said
    assert all(item.state == STATE_RUNNING for item in said)
    assert all(item.message is None for item in said)


def test_the_reason_survives_the_restart_budget_running_out(
    settings: CollectorSettings,
) -> None:
    """Попытки кончились, а причина осталась верной: счёт как был в евро, так и остался.

    Здесь менеджеру тем более нечего добавить: он уже ничего не делает, а на карточке
    стоит текст, который объясняет и почему процесс уходит, и что чинить.
    """
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    manager, _ = _manager(
        settings,
        api,
        spawn,
        between_ticks=lambda: spawn.kill_all(EXIT_ACCOUNT),
        max_restarts=2,
    )

    manager.run(max_ticks=6)

    assert len(spawn.children) == 1 + 2  # перезапуски всё-таки кончились
    final = api.report(-2)[A]
    assert final == HeartbeatAccount(account_id=A, state=STATE_RUNNING)


def test_a_silent_death_still_reaches_the_human(settings: CollectorSettings) -> None:
    """Обратная сторона: процесс, убитый системой, ничего сказать не успел.

    Тут сообщение менеджера — единственное, что есть, и молчать нельзя.
    """
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn, between_ticks=lambda: spawn.kill_all(CRASH))

    manager.run(max_ticks=2)

    told = api.report(-2)[A]
    assert told.state == STATE_ERROR
    assert told.message is not None
    assert "запускает его заново" in told.message


def test_a_death_in_the_window_between_reap_and_report_is_not_news_yet(
    settings: CollectorSettings,
) -> None:
    """Процесс умер после `_reap` — менеджер об этом ещё не знает и говорит от последнего `_reap`.

    Иначе отчёт собирался бы из двух источников сразу: живость свежая, а причина — от
    прошлой смерти, и человек получал бы «процесс завершился (код -9)» про процесс, который
    менеджер только что поднял. Смерть разбирается следующим тиком, целиком.

    Ребёнок здесь умирает внутри запроса assignments, то есть ровно в этом окне. Пятого
    тика хватает, чтобы к моменту второй такой смерти у счёта уже была история падений:
    без неё подмена незаметна.
    """
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn)
    api.on_assignments = lambda: spawn.kill_all(CRASH)

    manager.run(max_ticks=5)

    assert len(spawn.children) == 2  # первый умер, второй поднят после паузы
    assert api.report(4)[A] == HeartbeatAccount(account_id=A, state=STATE_RUNNING)
    assert all(
        "неизвестен" not in (item.message or "") for reported in api.heartbeats for item in reported
    )


def test_a_frozen_pool_does_not_promise_a_restart(settings: CollectorSettings) -> None:
    """Список счетов не пришёл — перезапусков не будет, и обещать их нельзя.

    Перезапуск живёт в `_apply`, а `_apply` пропускается, пока API молчит (решение, а не
    случайность: поднимать процесс без связи значит сжечь все попытки за пять минут).
    Пока это так, человек читает «жду связи», а не «запускаю заново».
    """
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()

    def die_and_go_silent() -> None:
        spawn.kill_all(CRASH)
        api.assignments_error = ApiError("TradeDesk не отвечает")

    manager, _ = _manager(settings, api, spawn, between_ticks=die_and_go_silent)

    manager.run(max_ticks=3)

    assert len(spawn.children) == 1  # перезапуска действительно не было
    told = api.report(-2)[A]
    assert told.state == STATE_ERROR
    assert told.message is not None
    assert "не перезапускает" in told.message
    assert "запускает его заново" not in told.message


def test_every_member_status_ends_in_a_decision(settings: CollectorSettings) -> None:
    """Новое состояние в `pool.MemberStatus` обязано получить текст или явное молчание.

    Без этой сверки забытое значение уронило бы отчёт `KeyError` — то есть менеджер
    перестал бы говорить обо **всех** счетах разом, а не только о новом состоянии.
    """
    assert set(get_args(pool.MemberStatus)) == set(manager_module.HEALTH_REPORTS)
    silent = {name for name, text in manager_module.HEALTH_REPORTS.items() if text is None}
    assert silent == {"running", "explained"}


# --------------------------------------------------------------------------------------
# Что менеджер говорит серверу
# --------------------------------------------------------------------------------------


def test_a_live_process_is_reported_without_a_message(settings: CollectorSettings) -> None:
    """`state=running` от менеджера не имеет права переписать причину, которую поставил счёт.

    Сообщение уезжает в `trading_accounts.status_message` и видно на экране; отсутствие
    сообщения его не трогает (`accounts.service.apply_heartbeat`).
    """
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn)

    manager.run(max_ticks=1)

    assert api.report(0)[A] == HeartbeatAccount(account_id=A, state=STATE_RUNNING)


def test_heartbeat_failure_does_not_stop_the_pool(settings: CollectorSettings) -> None:
    api = FakeManagerApi(accounts=[A], heartbeat_error=ApiError("TradeDesk не отвечает"))
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn)

    assert manager.run(max_ticks=2) == 0
    assert len(spawn.children) == 1


def test_shutdown_stops_children_and_says_the_collector_stopped(
    settings: CollectorSettings,
) -> None:
    api = FakeManagerApi(accounts=[A, B])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn)

    manager.run(max_ticks=1)

    assert all(child.terminated == 1 for child in spawn.children)
    farewell = api.heartbeats[-1]
    assert {item.state for item in farewell} == {STATE_STOPPED}
    assert {item.account_id for item in farewell} == {A, B}


def test_the_manager_crash_reaches_the_account_card(settings: CollectorSettings) -> None:
    """Единственный случай, когда о счёте рассказать буквально некому, — смерть менеджера.

    Его собственный текст уходит в `print` (консоли под Task Scheduler нет) и в файл лога,
    то есть на экран не попадает ничего: человек увидит «Коллектор остановлен», а через
    пять минут — «не на связи». Прощальный heartbeat `state=error` — единственный канал,
    в котором причина доедет до карточки.
    """
    api = FakeManagerApi(accounts=[A, B])
    spawn = FakeSpawn()

    def break_the_manager() -> None:
        api.assignments_crash = RuntimeError("boom")

    manager, _ = _manager(settings, api, spawn, between_ticks=break_the_manager)

    with pytest.raises(RuntimeError):
        manager.run(max_ticks=3)

    farewell = api.report(-1)
    assert {item.state for item in farewell.values()} == {STATE_ERROR}
    assert set(farewell) == {A, B}
    said = farewell[A].message
    assert said is not None
    assert "аварийно остановился" in said
    assert "RuntimeError" in said
    assert all(child.terminated == 1 for child in spawn.children)


def test_a_normal_stop_is_not_reported_as_a_failure(settings: CollectorSettings) -> None:
    """Остановку попросил человек: `stopped` статуса не меняет (`accounts.service`)."""
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    manager, _ = _manager(settings, api, spawn)

    manager.run(max_ticks=1)

    assert api.report(-1)[A].state == STATE_STOPPED


def test_a_stubborn_child_is_killed(settings: CollectorSettings) -> None:
    """Терминал завис в нативном вызове — `terminate` его не разбудит."""
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn(stubborn=True)
    manager, _ = _manager(settings, api, spawn)

    manager.run(max_ticks=1)

    assert spawn.children[0].terminated == 1
    assert spawn.children[0].killed == 1
    assert not spawn.children[0].alive


def test_stop_breaks_the_loop(settings: CollectorSettings) -> None:
    """Сигнал доходит до цикла, не дожидаясь конца минутной паузы."""
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    clock = Clock()

    def stopping_sleep(seconds: float) -> None:
        clock.value += seconds
        manager.stop()

    manager = Manager(
        settings=settings, api=api, spawn=spawn, sleep=stopping_sleep, monotonic=clock
    )

    manager.run(max_ticks=0)

    assert api.asked == 1
    assert clock.value == manager_module.NAP_SLICE_SECONDS


def test_the_pause_between_ticks_is_the_heartbeat_interval(
    settings: CollectorSettings,
) -> None:
    api = FakeManagerApi(accounts=[A])
    spawn = FakeSpawn()
    manager, clock = _manager(settings, api, spawn)

    manager.run(max_ticks=2)

    assert clock.value == float(settings.heartbeat_interval_seconds)


# --------------------------------------------------------------------------------------
# Точка входа
# --------------------------------------------------------------------------------------


def test_the_manager_refuses_to_run_outside_windows() -> None:
    """`SPEC.md` §8.3: на macOS коллектор не запускается и говорит об этом словами."""
    assert manager_module.main(["--once"]) == EXIT_PLATFORM


def test_parser_takes_an_env_file_and_a_single_tick() -> None:
    args = manager_module.build_parser().parse_args(["--once", "--env-file", "c:/x/collector.env"])
    assert args.once
    assert args.env_file == Path("c:/x/collector.env")


def test_manager_crash_message_names_the_log_file() -> None:
    assert "collector.log" in messages.MANAGER_CRASHED
    assert EXIT_FAILURE == 1


# --------------------------------------------------------------------------------------
# Настоящий `spawn`: скраб пароля в дочернем процессе
# --------------------------------------------------------------------------------------


class _StubAccountInfo:
    """Счёт не в USD: единственный способ дать процессу счёта закончиться самому.

    Валюта проверяется на первом же тике, и `worker` выходит с `EXIT_ACCOUNT`
    (`SPEC.md` §8.2). Пароль к этому моменту уже получен — значит, проверяемое состояние
    скраба сложилось целиком.
    """

    currency = "EUR"
    margin_mode = 2
    balance = 10_000.0
    equity = 10_000.0


class _StubTerminal:
    """Терминал, которого на macOS не существует. Ни одного решения внутри."""

    def __init__(self, **_kwargs: Any) -> None:
        return None

    def connect(self) -> None:
        return None

    def wait_for_history(self) -> None:
        return None

    def account_info(self) -> _StubAccountInfo:
        return _StubAccountInfo()

    def history_deals(self, start: Any, end: Any) -> list[Any]:
        return []

    def open_positions(self) -> list[Any]:
        return []

    def server_time(self) -> int | None:
        return None

    def close(self) -> None:
        return None


class _StubApiClient:
    """API дочернего процесса. Отдаёт задание с паролем — точку входа секрета в процесс."""

    def __init__(self, settings: Any) -> None:
        self._settings = settings

    def __enter__(self) -> _StubApiClient:
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def assignments(self, collector_id: str) -> list[Assignment]:
        return [
            Assignment(
                account_id=CHILD_ACCOUNT,
                server="E-Global-Real",
                login=1234567,
                password=CHILD_PASSWORD,
                sync_requested_at=None,
                last_sync_at=None,
                status="pending",
            )
        ]

    def send_deals(self, batch: dict[str, Any]) -> Any:  # pragma: no cover — счёт не в USD
        raise AssertionError("батч не должен уехать: счёт не в USD")

    def heartbeat(self, collector_id: str, accounts: Iterable[HeartbeatAccount]) -> None:
        return None


def _no_refusal(system: str | None = None) -> str | None:
    """Подмена `platform_refusal`: на macOS её отказ не даёт ребёнку дойти до старта."""
    return None


def _child_probe(
    env_file: str,
    queue: multiprocessing.queues.Queue[tuple[str, tuple[str, ...]]],
) -> None:
    """Выполняется в НАСТОЯЩЕМ дочернем процессе, поднятом через `spawn`.

    Терминал и HTTP подменяются здесь, а не в родителе, и это не обход проверки: при
    `spawn` родительские подмены до ребёнка не доезжают вовсе — ровно то свойство,
    которое тест и измеряет.
    """
    from collector import logging_setup as child_logging
    from collector import main as child_main
    from collector import worker as child_worker

    queue.put(("inherited", child_logging.known_secrets()))
    child_worker.platform_refusal = _no_refusal
    child_worker.ApiClient = _StubApiClient  # type: ignore[misc,assignment]
    child_worker.Mt5Terminal = _StubTerminal  # type: ignore[misc,assignment]
    code = 0
    try:
        child_main.run_account(CHILD_ACCOUNT, env_file)
    except SystemExit as stop:
        code = int(stop.code or 0)
    queue.put(("exit", (str(code),)))
    queue.put(("after", child_logging.known_secrets()))


def _write_env(tmp_path: Path) -> Path:
    env_file = tmp_path / "collector.env"
    env_file.write_text(
        "\n".join(
            [
                "API_URL=http://localhost:8000",
                f"COLLECTOR_TOKEN={TOKEN}",
                f"COLLECTOR_ID={COLLECTOR_ID}",
                f"MT5_TERMINAL_EXE={tmp_path / 'terminal64.exe'}",
                f"MT5_PORTABLE_ROOT={tmp_path / 'td-terminals'}",
                f"LOG_DIR={tmp_path / 'logs'}",
            ]
        ),
        encoding="utf-8",
    )
    return env_file


def test_spawned_child_builds_its_own_password_scrub(tmp_path: Path) -> None:
    """`CLAUDE.md` §5 в дочернем процессе: пароль попадает в скраб, и не по наследству.

    Проверяются оба утверждения сразу, потому что порознь каждое ничего не значит.

    1. Ребёнок стартует с **пустым** реестром секретов, хотя родитель свой заполнил, —
       так `spawn` и устроен, а на Windows другого способа завести процесс нет.
    2. После своего старта (`run_account` → `worker.main`) в реестре ребёнка лежат оба
       секрета: токен из `collector.env` и пароль счёта из assignments.

    Не «мы полагаем, что ребёнок настроит скраб сам», а измерено настоящим процессом.
    """
    context = multiprocessing.get_context(manager_module.SPAWN)
    assert context.get_start_method() == "spawn"

    logging_setup.register_secret("parent-only-secret-value")
    queue: multiprocessing.queues.Queue[tuple[str, tuple[str, ...]]] = context.Queue()
    process = context.Process(target=_child_probe, args=(str(_write_env(tmp_path)), queue))
    process.start()
    try:
        seen = dict(queue.get(timeout=60) for _ in range(3))
    finally:
        process.join(60)
        if process.is_alive():  # pragma: no cover — ребёнок не должен зависать
            process.kill()
            process.join(10)

    assert seen["inherited"] == ()
    assert seen["exit"] == (str(EXIT_ACCOUNT),)
    assert TOKEN in seen["after"]
    assert CHILD_PASSWORD in seen["after"]
    assert "parent-only-secret-value" not in seen["after"]


def test_the_child_gets_the_account_and_the_env_file_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Пароль через границу процессов не передаётся: ребёнок берёт его сам.

    Аргументы дочернего процесса уезжают в pickle-буфер спавна и видны в списке процессов
    Windows — пароля в них быть не должно (`CLAUDE.md` §5).
    """
    seen: list[Sequence[str]] = []

    def fake_main(argv: Sequence[str] | None = None) -> int:
        seen.append(list(argv or []))
        return EXIT_ACCOUNT

    monkeypatch.setattr(manager_module.worker, "main", fake_main)
    with pytest.raises(SystemExit) as stop:
        manager_module.run_account(CHILD_ACCOUNT, "C:\\td\\collector.env")

    assert stop.value.code == EXIT_ACCOUNT
    assert seen == [["--account-id", CHILD_ACCOUNT, "--env-file", "C:\\td\\collector.env"]]
