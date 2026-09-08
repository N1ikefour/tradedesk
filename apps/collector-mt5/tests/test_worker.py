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

from collector import messages, state
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


def _worker(
    settings: CollectorSettings,
    api: FakeApi,
    terminal: FakeTerminal,
    *,
    state_file: Path | None = None,
    now: Any = None,
    between_ticks: Any = None,
) -> AccountWorker:
    """Цикл с подделками. `between_ticks` — что произошло в мире, пока коллектор спал."""
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
    assert _worker(settings, api, terminal).run(max_ticks=1) == EXIT_OK
    assert api.batches == []
    error = next(beat for beat in api.heartbeats if beat.state == "error")
    assert error.message == messages.OFFSET_UNKNOWN


def test_remembered_offset_carries_a_closed_market(
    settings: CollectorSettings, assignment: Assignment, tmp_path: Path
) -> None:
    """Перезапуск в выходной иначе означал бы простой до открытия рынка."""
    state_file = tmp_path / "collector-state.json"
    state.write_state(state_file, state.WorkerState(server_utc_offset_minutes=120))
    api, terminal = _ready(assignment, deals=[deal()], tick_time=None)
    assert _worker(settings, api, terminal, state_file=state_file).run(max_ticks=1) == EXIT_OK
    assert api.batches[0]["server_utc_offset_minutes"] == 120


def test_a_fresh_offset_is_written_down(
    settings: CollectorSettings, assignment: Assignment, tmp_path: Path
) -> None:
    state_file = tmp_path / "collector-state.json"
    api, terminal = _ready(assignment, deals=[deal()])
    _worker(settings, api, terminal, state_file=state_file).run(max_ticks=1)
    assert state.read_state(state_file).server_utc_offset_minutes == 120


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
