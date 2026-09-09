"""Цикл одного счёта на подделках — SPEC.md 8.2, пункт 2.

Терминала на машине разработки нет, поэтому проверяется всё, что цикл **решает**:
что тянуть, что отправлять, когда молчать, что сказать человеку при отказе. Что цикл
получит от настоящего терминала — не проверяется здесь ничем и перечислено в итоге
задачи отдельным списком.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from collector import logging_setup, messages, state
from collector import worker as worker_module
from collector.api_client import ApiError, Assignment
from collector.config import CollectorSettings
from collector.mt5_client import TerminalError
from collector.worker import EXIT_ACCOUNT, EXIT_OK, AccountWorker, build_parser
from tests.conftest import (
    ACCOUNT_ID,
    FakeAccountInfo,
    FakeApi,
    FakePosition,
    FakeTerminal,
    deal,
    moment,
)

NOW = moment()
# Тик от того же брокера, что в выгрузке 7 сентября 2026: смещение +120 минут.
BROKER_TICK = int((NOW + timedelta(minutes=120)).timestamp())


class _Recorder:
    """Подставной логгер: проверяется не формат строки, а сам факт, что она есть."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def _record(self, event: str, **fields: Any) -> None:
        self.events.append((event, fields))

    debug = info = warning = error = exception = _record

    def find(self, event: str) -> dict[str, Any]:
        return next(fields for name, fields in self.events if name == event)


def _worker(
    settings: CollectorSettings,
    api: FakeApi,
    terminal: FakeTerminal,
    *,
    state_file: Path | None = None,
    known_offset: int | None = 120,
    now: Any = None,
    between_ticks: Any = None,
) -> AccountWorker:
    """Цикл с подделками. `between_ticks` — что произошло в мире, пока коллектор спал.

    По умолчанию смещение уже подтверждено прошлым запуском — так выглядит счёт, который
    хоть раз синхронизировался. `known_offset=None` — счёт, поднятый впервые: первый тик
    у него уходит на сверку часов брокера, и батч уезжает только со второго.
    """
    if state_file is None and known_offset is not None:
        state_file = settings.mt5_portable_root / "known-offset.json"
        state.write_state(state_file, state.WorkerState(server_utc_offset_minutes=known_offset))
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        if between_ticks is not None:
            between_ticks()

    worker = AccountWorker(
        account_id=ACCOUNT_ID,
        settings=settings,
        api=api,
        terminal_factory=lambda _assignment: terminal,
        clock=now or (lambda: NOW),
        sleep=sleep,
        state_file=state_file,
    )
    worker.slept = slept  # type: ignore[attr-defined]
    return worker


def _ready(assignment: Assignment, **terminal: Any) -> tuple[FakeApi, FakeTerminal]:
    api = FakeApi(assignment=assignment)
    terminal_kwargs: dict[str, Any] = {"tick_time": BROKER_TICK}
    terminal_kwargs.update(terminal)
    return api, FakeTerminal(**terminal_kwargs)


# --------------------------------------------------------------------------------------
# Счастливый путь
# --------------------------------------------------------------------------------------


def test_first_pass_sends_the_history_it_found(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    api, terminal = _ready(assignment, deals=[deal(ticket=1, at=200), deal(ticket=2, at=100)])
    assert _worker(settings, api, terminal).run(max_ticks=1) == EXIT_OK

    assert len(api.batches) == 1
    batch = api.batches[0]
    assert batch["account_id"] == ACCOUNT_ID
    assert batch["source"] == "collector"
    assert batch["server_utc_offset_minutes"] == 120
    assert [item["ticket"] for item in batch["deals"]] == [2, 1]


def test_open_positions_ride_along_with_every_batch(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Пустой список по контракту значит «открытых нет» — промежуточный батч соврал бы."""
    api, terminal = _ready(assignment, deals=[deal()], positions=[FakePosition(identifier=55)])
    _worker(settings, api, terminal).run(max_ticks=1)
    assert api.batches[0]["open_positions"][0]["position_id"] == 55


def test_a_long_history_leaves_in_batches_of_five_thousand(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """SPEC.md 5.3: больше 5000 — 413. Разбивать, а не получать отказ."""
    deals = [deal(ticket=n, at=1_788_000_000 + n) for n in range(5001)]
    api, terminal = _ready(assignment, deals=deals)
    _worker(settings, api, terminal).run(max_ticks=1)
    assert [len(batch["deals"]) for batch in api.batches] == [5000, 1]


def test_heartbeat_says_the_account_is_running(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    api, terminal = _ready(assignment, deals=[deal()])
    _worker(settings, api, terminal).run(max_ticks=1)
    states = [beat.state for beat in api.heartbeats]
    assert "running" in states
    assert states[-1] == "stopped"


# --------------------------------------------------------------------------------------
# Окно и перезапуск
# --------------------------------------------------------------------------------------


def test_window_is_asked_in_broker_hours(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Иначе окно уезжает на смещение и сделки у края теряются молча."""
    api, terminal = _ready(assignment, deals=[deal()])
    _worker(settings, api, terminal).run(max_ticks=1)
    start, end = terminal.history_calls[0]
    assert start.tzinfo is None
    assert end == (NOW + timedelta(days=1, minutes=120)).replace(tzinfo=None)


def test_restart_asks_for_the_overlapping_window_again(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Перезапуск не создаёт дублей: окно перекрывается, дедупликация — на сервере."""
    synced = Assignment(
        account_id=assignment.account_id,
        server=assignment.server,
        login=assignment.login,
        password=assignment.password,
        sync_requested_at=None,
        last_sync_at=NOW - timedelta(hours=2),
        status="connected",
    )
    api, terminal = _ready(synced, deals=[deal()])
    _worker(settings, api, terminal).run(max_ticks=1)
    start, _ = terminal.history_calls[0]
    assert start == (NOW - timedelta(hours=26) + timedelta(minutes=120)).replace(tzinfo=None)


def test_sync_now_widens_the_window(settings: CollectorSettings, assignment: Assignment) -> None:
    requested = Assignment(
        account_id=assignment.account_id,
        server=assignment.server,
        login=assignment.login,
        password=assignment.password,
        sync_requested_at=NOW - timedelta(minutes=1),
        last_sync_at=NOW - timedelta(hours=2),
        status="connected",
    )
    api, terminal = _ready(requested, deals=[deal()])
    _worker(settings, api, terminal).run(max_ticks=1)
    start, _ = terminal.history_calls[0]
    assert start < (NOW - timedelta(days=29)).replace(tzinfo=None)


# --------------------------------------------------------------------------------------
# Молчание
# --------------------------------------------------------------------------------------


def test_nothing_new_means_no_second_batch(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Иначе `sync_runs` наполнялся бы одинаковыми строками раз в минуту."""
    api, terminal = _ready(assignment, deals=[deal()])
    assert _worker(settings, api, terminal).run(max_ticks=3) == EXIT_OK
    assert len(api.batches) == 1


def test_a_new_deal_breaks_the_silence(settings: CollectorSettings, assignment: Assignment) -> None:
    api, terminal = _ready(assignment, deals=[deal(ticket=1)])
    worker = _worker(
        settings,
        api,
        terminal,
        between_ticks=lambda: terminal.deals.append(deal(ticket=2, at=1_788_400_000)),
    )
    worker.run(max_ticks=2)
    assert len(api.batches) == 2
    assert [item["ticket"] for item in api.batches[1]["deals"]] == [1, 2]


def test_a_closed_position_breaks_the_silence(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    api, terminal = _ready(assignment, deals=[deal()], positions=[FakePosition()])
    worker = _worker(settings, api, terminal, between_ticks=terminal.positions.clear)
    worker.run(max_ticks=2)
    assert len(api.batches) == 2
    assert api.batches[1]["open_positions"] == []


# --------------------------------------------------------------------------------------
# Отказы, которые увидит человек
# --------------------------------------------------------------------------------------


def test_wrong_password_reaches_the_account_card_in_words(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """S1-10 DoD: неверный пароль виден в UI как «Неверный пароль инвестора»."""
    failure = TerminalError(
        messages.describe_mt5_failure(
            messages.RES_E_AUTH_FAILED,
            "Terminal: Authorization failed",
            stage="connect",
            server=assignment.server,
            login=assignment.login,
        ),
        code=messages.RES_E_AUTH_FAILED,
    )
    api, terminal = _ready(assignment, connect_errors=[failure])
    worker = _worker(settings, api, terminal)
    assert worker.run(max_connect_attempts=1) == EXIT_ACCOUNT

    error = next(beat for beat in api.heartbeats if beat.state == "error")
    assert error.message is not None
    assert error.message.startswith("Неверный пароль инвестора")
    assert api.batches == []


def test_connection_is_retried_with_growing_delay(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """SPEC.md 8.2: экспоненциальная задержка до 15 минут, а не отказ с первой попытки."""
    api, terminal = _ready(
        assignment,
        deals=[deal()],
        connect_errors=[TerminalError("раз", code=-10005), TerminalError("два", code=-10005)],
    )
    worker = _worker(settings, api, terminal)
    assert worker.run(max_ticks=1) == EXIT_OK
    assert terminal.connected == 3
    assert worker.slept[:2] == [5.0, 10.0]  # type: ignore[attr-defined]


def test_non_usd_account_stops_instead_of_syncing(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """SPEC.md 8.2: «Счёт не в USD» — синк не выполняется (v1)."""
    api, terminal = _ready(assignment, deals=[deal()], info=FakeAccountInfo(currency="EUR"))
    assert _worker(settings, api, terminal).run(max_ticks=1) == EXIT_ACCOUNT
    error = next(beat for beat in api.heartbeats if beat.state == "error")
    assert error.message is not None
    assert error.message.startswith("Счёт не в USD")
    assert api.batches == []


def test_account_not_assigned_says_where_to_look(settings: CollectorSettings) -> None:
    api = FakeApi(assignment=None)
    assert _worker(settings, api, FakeTerminal()).run(max_ticks=1) == EXIT_ACCOUNT
    assert api.heartbeats[0].message is not None
    assert "COLLECTOR_ID" in api.heartbeats[0].message


def test_a_refused_batch_is_reported_and_retried_next_tick(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Отказ API не роняет процесс: следующая итерация заберёт то же окно (роль collector)."""
    api, terminal = _ready(assignment, deals=[deal()])
    api.refuse = ApiError("Счёт архивирован", code="account_archived", status=422)

    def recover() -> None:
        api.refuse = None

    worker = _worker(settings, api, terminal, between_ticks=recover)
    assert worker.run(max_ticks=2) == EXIT_OK

    error = next(beat for beat in api.heartbeats if beat.state == "error")
    assert error.message is not None
    assert "Счёт архивирован" in error.message
    assert len(api.batches) == 1


def test_a_deal_the_server_would_refuse_does_not_stop_the_account(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Одна кривая сделка иначе даёт 400 на весь батч — и счёт стоит навсегда."""
    api, terminal = _ready(
        assignment,
        deals=[deal(ticket=1), deal(ticket=2, at=1_788_400_000, symbol="EUR USD")],
    )
    _worker(settings, api, terminal).run(max_ticks=1)
    assert [deal["ticket"] for deal in api.batches[0]["deals"]] == [1]
    running = next(beat for beat in api.heartbeats if beat.state == "running")
    assert running.message is not None
    assert "тикет 2" in running.message
    assert "пробелы" in running.message


def test_an_open_position_the_server_would_refuse_does_not_stop_the_account(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Отбраковка симметрична сделкам, и здесь она важнее.

    Открытые позиции едут в каждом чанке окна: негодная позиция отвергала бы не один
    батч, а все подряд, и счёт вставал бы навсегда — ретрай такое не чинит.
    """
    api, terminal = _ready(
        assignment,
        deals=[deal()],
        positions=[FakePosition(identifier=1), FakePosition(identifier=2, type=7)],
    )
    _worker(settings, api, terminal).run(max_ticks=1)

    assert [item["position_id"] for item in api.batches[0]["open_positions"]] == [1]
    running = next(beat for beat in api.heartbeats if beat.state == "running")
    assert running.message is not None
    assert "позиция 2" in running.message
    assert "тип позиции" in running.message


def test_a_refused_position_leaves_the_position_open_on_the_server(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Цена отбраковки названа числом: из записи `open_positions` сервер читает один id.

    `position_builder` ставит `status='closed'` только когда объёмы сошлись в ноль **и**
    записи нет; у настоящей открытой позиции объёмы не сходятся, поэтому потеря записи
    её не закрывает. Здесь фиксируется то, что от неё зависит: набор id для `decide_send`.
    """
    api, terminal = _ready(
        assignment, deals=[deal()], positions=[FakePosition(identifier=2, symbol="")]
    )
    worker = _worker(settings, api, terminal)
    worker.run(max_ticks=1)
    assert api.batches[0]["open_positions"] == []


def test_an_untranslatable_account_info_stops_with_words_instead_of_a_traceback(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Неизвестный режим счёта — не повод умереть молча.

    Трейсбек ушёл бы в `sys.excepthook`, то есть в консоль, которой под Task Scheduler
    нет: в `account-<id>.log` не попало бы ничего, а `S1-09` крутил бы краш-петлю.
    """
    api, terminal = _ready(assignment, deals=[deal()], info=FakeAccountInfo(margin_mode=9))
    assert _worker(settings, api, terminal).run(max_ticks=2) == EXIT_OK

    assert api.batches == []
    error = next(beat for beat in api.heartbeats if beat.state == "error")
    assert error.message is not None
    assert "неизвестный режим счёта 9" in error.message
    assert terminal.closed == 1


def test_a_clock_behind_the_server_does_not_turn_the_window_inside_out(
    settings: CollectorSettings, assignment: Assignment, monkeypatch: Any
) -> None:
    """`last_sync_at` из будущего давал `start > end`: история не вернёт ничего и не может.

    Триггер бытовой — часы машины пользователя отстают от серверных. Симптом злой: батчи
    уходят пустыми, сервер пишет ещё более свежий `last_sync_at`, а на экране «синхронизация
    идёт». Окно чинится, причина попадает в лог.
    """
    events = _Recorder()
    monkeypatch.setattr(worker_module, "log", events)
    from_the_future = Assignment(
        account_id=assignment.account_id,
        server=assignment.server,
        login=assignment.login,
        password=assignment.password,
        sync_requested_at=None,
        last_sync_at=NOW + timedelta(days=3),
        status="connected",
    )
    api, terminal = _ready(from_the_future, deals=[deal()])
    _worker(settings, api, terminal).run(max_ticks=1)

    start, end = terminal.history_calls[0]
    assert start < end
    assert start == (NOW - timedelta(hours=24) + timedelta(minutes=120)).replace(tzinfo=None)
    assert events.find("collector.clock_behind_server")


def test_a_failed_heartbeat_does_not_stop_the_sync(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Сделки важнее отметки о состоянии: heartbeat повторится через минуту."""

    class SilentApi(FakeApi):
        def heartbeat(self, collector_id: str, accounts: Any) -> None:
            raise ApiError("нет связи")

    api = SilentApi(assignment=assignment)
    terminal = FakeTerminal(tick_time=BROKER_TICK, deals=[deal()])
    assert _worker(settings, api, terminal).run(max_ticks=1) == EXIT_OK
    assert len(api.batches) == 1


# --------------------------------------------------------------------------------------
# Смещение часов брокера
# --------------------------------------------------------------------------------------


def test_no_quote_means_no_batch_and_a_readable_reason(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Смещение обязательно в каждом батче: без него отправлять нечего, и это говорится."""
    api, terminal = _ready(assignment, deals=[deal()], tick_time=None)
    assert _worker(settings, api, terminal, known_offset=None).run(max_ticks=1) == EXIT_OK
    assert api.batches == []
    error = next(beat for beat in api.heartbeats if beat.state == "error")
    assert error.message == messages.OFFSET_UNKNOWN


def test_the_first_offset_waits_for_a_second_quote(
    settings: CollectorSettings, assignment: Assignment, tmp_path: Path
) -> None:
    """Первое значение не принимается на веру — на одном тике отправлять нечем.

    Цена решения названа прямо: первый в жизни счёта батч уезжает не сразу, а через один
    цикл опроса. Дальше смещение живёт в файле состояния и перезапуск его не теряет.
    """
    state_file = tmp_path / "collector-state.json"
    api, terminal = _ready(assignment, deals=[deal()])
    worker = _worker(settings, api, terminal, state_file=state_file)

    assert worker.run(max_ticks=1) == EXIT_OK
    assert api.batches == []
    assert state.read_state(state_file).server_utc_offset_minutes is None
    waiting = next(beat for beat in api.heartbeats if beat.message == messages.OFFSET_PENDING)
    assert waiting.state == "running"


def test_a_stale_first_quote_does_not_poison_the_state_forever(
    settings: CollectorSettings, assignment: Assignment, tmp_path: Path
) -> None:
    """Разбор боевого сценария: тонкий рынок, котировка пятичасовой давности, первый запуск.

    Прежде такое значение (−180 вместо +120) уезжало в батч и записывалось в
    `collector-state.json`, после чего правильное смещение отвергалось как «скачок больше
    DST» — навсегда, до ручного удаления файла. Проверяется именно это: в батч и в файл
    попадает +120, то есть отравления не случилось.
    """
    state_file = tmp_path / "collector-state.json"
    stale = int((NOW - timedelta(minutes=180)).timestamp())
    api, terminal = _ready(assignment, deals=[deal()], tick_time=stale, tick_step=0)

    def market_opens() -> None:
        terminal.tick_time = BROKER_TICK
        terminal.tick_step = 60

    worker = _worker(settings, api, terminal, state_file=state_file, between_ticks=market_opens)
    assert worker.run(max_ticks=3) == EXIT_OK

    assert state.read_state(state_file).server_utc_offset_minutes == 120
    assert [batch["server_utc_offset_minutes"] for batch in api.batches] == [120]


def test_a_frozen_quote_is_not_a_second_opinion(
    settings: CollectorSettings, assignment: Assignment, tmp_path: Path
) -> None:
    """Повтор по той же котировке ничего не доказывает — и не должен считаться за второй.

    У застывшего тика смещение между опросами не меняется: минута разницы съедается
    округлением до четверти часа. Подтверждает только **обновившаяся** котировка.
    """
    state_file = tmp_path / "collector-state.json"
    stale = int((NOW - timedelta(minutes=180)).timestamp())
    api, terminal = _ready(assignment, deals=[deal()], tick_time=stale, tick_step=0)
    assert _worker(settings, api, terminal, state_file=state_file).run(max_ticks=5) == EXIT_OK
    assert api.batches == []
    assert state.read_state(state_file).server_utc_offset_minutes is None


def test_remembered_offset_carries_a_closed_market(
    settings: CollectorSettings, assignment: Assignment, tmp_path: Path
) -> None:
    """Перезапуск в выходной иначе означал бы простой до открытия рынка."""
    state_file = tmp_path / "collector-state.json"
    state.write_state(state_file, state.WorkerState(server_utc_offset_minutes=120))
    api, terminal = _ready(assignment, deals=[deal()], tick_time=None)
    assert _worker(settings, api, terminal, state_file=state_file).run(max_ticks=1) == EXIT_OK
    assert api.batches[0]["server_utc_offset_minutes"] == 120


def test_a_confirmed_offset_is_written_down(
    settings: CollectorSettings, assignment: Assignment, tmp_path: Path
) -> None:
    """На диск попадает только то, что подтверждено второй котировкой."""
    state_file = tmp_path / "collector-state.json"
    api, terminal = _ready(assignment, deals=[deal()])
    _worker(settings, api, terminal, state_file=state_file).run(max_ticks=2)
    assert state.read_state(state_file).server_utc_offset_minutes == 120
    assert api.batches[0]["server_utc_offset_minutes"] == 120


def test_a_stale_quote_does_not_overwrite_a_known_offset(
    settings: CollectorSettings, assignment: Assignment, tmp_path: Path
) -> None:
    """Прошлые сделки не пересчитываются (SPEC.md 6.3) — чужое смещение портит их навсегда."""
    state_file = tmp_path / "collector-state.json"
    state.write_state(state_file, state.WorkerState(server_utc_offset_minutes=120))
    stale = int((NOW + timedelta(hours=10)).timestamp())
    api, terminal = _ready(assignment, deals=[deal()], tick_time=stale)
    _worker(settings, api, terminal, state_file=state_file).run(max_ticks=1)
    assert api.batches[0]["server_utc_offset_minutes"] == 120


def test_a_refused_candidate_leaves_a_line_in_the_log(
    settings: CollectorSettings, assignment: Assignment, tmp_path: Path, monkeypatch: Any
) -> None:
    """Отказ обязан быть виден: молча отвергнутое смещение — тишина вместо диагноза.

    Симптом отравленного состояния именно такой: коллектор каждую минуту получает
    правильные +120, каждую минуту их выбрасывает, и в логе нет ни строки.
    """
    events = _Recorder()
    monkeypatch.setattr(worker_module, "log", events)
    state_file = tmp_path / "collector-state.json"
    state.write_state(state_file, state.WorkerState(server_utc_offset_minutes=120))
    stale = int((NOW + timedelta(hours=10)).timestamp())
    api, terminal = _ready(assignment, deals=[deal()], tick_time=stale)
    _worker(settings, api, terminal, state_file=state_file).run(max_ticks=1)

    rejected = events.find("collector.offset_rejected")
    assert rejected["status"] == "jump_refused"
    assert rejected["candidate"] == 600
    assert rejected["known"] == 120


def test_a_clock_that_is_hours_off_says_so_instead_of_blaming_the_market(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Второй по вероятности повод «смещения нет» — сбитые часы машины, а не выходной."""
    broken = int((NOW + timedelta(hours=20)).timestamp())
    api, terminal = _ready(assignment, deals=[deal()], tick_time=broken)
    assert _worker(settings, api, terminal, known_offset=None).run(max_ticks=1) == EXIT_OK
    assert api.batches == []
    error = next(beat for beat in api.heartbeats if beat.state == "error")
    assert error.message is not None
    assert "часовой пояс Windows" in error.message
    assert "+20 ч" in error.message


# --------------------------------------------------------------------------------------
# Пароль счёта
# --------------------------------------------------------------------------------------


def test_the_account_password_never_reaches_the_log_file(
    settings: CollectorSettings, assignment: Assignment, tmp_path: Path, monkeypatch: Any
) -> None:
    """Инвариант `CLAUDE.md` §5 — механизмом, а не дисциплиной автора.

    Прогон настоящий: логи поднимаются так же, как в `main()`, и знают при старте только
    токен из `collector.env` — пароля счёта тогда ещё не существует. Утечка изображается
    тем единственным способом, каким она и случается: пароль внутри текста ошибки от
    чужой библиотеки, который коллектор честно кладёт в лог как причину отказа.

    Логгер модуля пересоздаётся из-за `cache_logger_on_first_use`: proxy, once bound,
    держит конфигурацию, которая была активна в момент первой записи, а её в тестах
    задаёт порядок файлов. Проверяется от этого не меньше — цепочка процессоров, хендлер
    и файл настоящие.
    """
    log_file = tmp_path / "logs" / "account-test.log"
    logging_setup.setup_logging(log_file=log_file, level="INFO", secrets=settings.secrets)
    monkeypatch.setattr(worker_module, "log", logging_setup.get_logger("collector.worker"))

    leak = TerminalError(f"IPC initialize failed (login=1234567 password={assignment.password})")
    api, terminal = _ready(assignment, connect_errors=[leak])
    assert _worker(settings, api, terminal).run(max_connect_attempts=1) == EXIT_ACCOUNT

    written = log_file.read_text(encoding="utf-8")
    assert "collector.connect_failed" in written
    assert assignment.password not in written
    assert logging_setup.SECRET_PLACEHOLDER in written


def test_the_account_password_never_reaches_the_account_card(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Второй канал, которым текст ошибки уходит из процесса, — `status_message` на экране."""
    leak = TerminalError(f"IPC initialize failed password={assignment.password}")
    api, terminal = _ready(assignment, connect_errors=[leak])
    _worker(settings, api, terminal).run(max_connect_attempts=1)

    beat = next(item for item in api.heartbeats if item.state == "error")
    body = beat.payload()
    assert assignment.password not in body["message"]
    assert logging_setup.SECRET_PLACEHOLDER in body["message"]


# --------------------------------------------------------------------------------------
# Командная строка
# --------------------------------------------------------------------------------------


def test_account_id_is_required() -> None:
    """S1-08: ручной запуск с `--account-id`; менеджер процессов — S1-09."""
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_parser_accepts_the_documented_flags() -> None:
    args = build_parser().parse_args(["--account-id", ACCOUNT_ID, "--once"])
    assert args.account_id == ACCOUNT_ID
    assert args.once is True
    assert args.env_file == Path("collector.env")


def test_a_terminal_that_died_mid_run_is_reconnected(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """Терминал закрывают руками, он падает, машина уходит в сон.

    Без переподключения процесс остался бы жив, слал бы одну и ту же ошибку каждую
    минуту и не синхронизировал ничего до ручного перезапуска.
    """
    api, _unused = _ready(assignment, deals=[deal()])

    class DyingTerminal(FakeTerminal):
        alive: bool = True

        def account_info(self) -> FakeAccountInfo:
            if not self.alive:
                self.alive = True
                raise TerminalError("терминал закрылся", code=-10004)
            return self.info

    dying = DyingTerminal(tick_time=BROKER_TICK, deals=[deal()])
    worker = _worker(settings, api, dying, between_ticks=lambda: setattr(dying, "alive", False))
    assert worker.run(max_ticks=2) == EXIT_OK

    assert dying.connected == 2
    assert dying.closed >= 1
    assert any(beat.state == "error" for beat in api.heartbeats)


def test_a_deal_out_of_ticket_order_still_counts_as_new(
    settings: CollectorSettings, assignment: Assignment
) -> None:
    """«Новее последнего тикета» считается по максимуму, а не по хвосту хронологии.

    Монотонность тикетов MT5 нам никто не обещал; сделка с большим тикетом и более ранним
    временем иначе не разбудила бы отправку и повисла бы до keepalive.
    """
    api, terminal = _ready(assignment, deals=[deal(ticket=10, at=1_788_400_000)])
    worker = _worker(
        settings,
        api,
        terminal,
        between_ticks=lambda: terminal.deals.append(deal(ticket=99, at=1_788_100_000)),
    )
    worker.run(max_ticks=2)
    assert len(api.batches) == 2


def test_an_unexpected_crash_lands_in_the_log_instead_of_a_missing_console(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Под Task Scheduler (`S1-10`) консоли нет, и `sys.excepthook` пишет в никуда.

    Без этого рубежа краш-петля из-под `S1-09` не оставляла бы ни строки: последний
    heartbeat — безобидный `stopped`, который на карточке не меняет ничего, в файле лога
    пусто, и разбираться не с чем.

    ⚠️ Проверяется и **отправка** причины, а не только запись в файл. Менеджер (`S1-09`)
    читает код 4 как «процесс уже объяснил человеку свой уход» и своего текста поверх не
    пишет; этот путь — единственный, который возвращает 4, ничего не сказав. Замолчи он
    здесь — на карточке осталось бы предыдущее сообщение, то есть неправда.
    """
    sent: list[Any] = []

    class _StubApi:
        """API без сети: настоящий клиент ретраил бы отправку две минуты."""

        def __init__(self, _settings: Any) -> None:
            return None

        def __enter__(self) -> _StubApi:
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

        def heartbeat(self, collector_id: str, accounts: Any) -> None:
            sent.extend(accounts)

    monkeypatch.setattr(worker_module, "ApiClient", _StubApi)
    env_file = tmp_path / "collector.env"
    env_file.write_text(
        "\n".join(
            [
                "API_URL=http://localhost:8000",
                "COLLECTOR_TOKEN=collector-token-0123456789",
                "COLLECTOR_ID=test-machine",
                f"MT5_TERMINAL_EXE={tmp_path / 'terminal64.exe'}",
                f"MT5_PORTABLE_ROOT={tmp_path / 'td-terminals'}",
                f"LOG_DIR={tmp_path / 'logs'}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(worker_module, "platform_refusal", lambda: None)
    monkeypatch.setattr(
        worker_module.AccountWorker,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("библиотека сломалась")),
    )
    monkeypatch.setattr(worker_module, "log", logging_setup.get_logger("collector.worker"))

    code = worker_module.main(["--account-id", ACCOUNT_ID, "--env-file", str(env_file), "--once"])

    assert code == EXIT_ACCOUNT
    written = (tmp_path / "logs" / f"account-{ACCOUNT_ID}.log").read_text(encoding="utf-8")
    assert "collector.crashed" in written
    assert "RuntimeError" in written

    assert [beat.state for beat in sent] == ["error"]
    assert sent[0].message is not None
    assert "RuntimeError" in sent[0].message
