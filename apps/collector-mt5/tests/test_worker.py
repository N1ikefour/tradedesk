"""Синхронизация одного счёта на подделках — SPEC.md 8.2, пункт 2.

Терминала на машине разработки нет, поэтому проверяется всё, что цикл **решает**: что
тянуть, что отправлять, когда молчать, что сказать человеку при отказе и — с `X-66` — когда
не отправлять вовсе, потому что счёт в терминале уже не тот. Что цикл получит от настоящего
терминала, здесь не проверяется ничем и перечислено в итоге задачи отдельным списком.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from collector import messages, payload, state
from collector import worker as worker_module
from collector.api_client import ApiError, Assignment, IngestResult
from collector.config import CollectorSettings
from collector.mt5_client import TerminalError
from collector.worker import STATE_ERROR, STATE_RUNNING, AccountWorker, Report
from tests.conftest import (
    ACCOUNT_ID,
    LOGIN,
    SERVER,
    FakeAccountInfo,
    FakeApi,
    FakePosition,
    FakeTerminal,
    assignment_for,
    deal,
    garbled_account_info,
    moment,
)

NOW = moment()
# Тик от того же брокера, что в выгрузке 7 сентября 2026: смещение +120 минут.
BROKER_TICK = int((NOW + timedelta(minutes=120)).timestamp())
# Счёт, на который человек переключается посреди работы коллектора.
OTHER_LOGIN = 999111


class _Recorder:
    """Подставной логгер: проверяется не формат строки, а сам факт, что она есть."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def _record(self, event: str, **fields: Any) -> None:
        self.events.append((event, fields))

    debug = info = warning = error = exception = _record

    def find(self, event: str) -> dict[str, Any]:
        return next(fields for name, fields in self.events if name == event)

    def has(self, event: str) -> bool:
        return any(name == event for name, _ in self.events)


@dataclass
class _ApiThatSwitchesTheTerminal(FakeApi):
    """API, на ответе которого человек успевает переключить счёт в терминале."""

    terminal: FakeTerminal | None = None

    def send_deals(self, batch: dict[str, Any]) -> IngestResult:
        result = super().send_deals(batch)
        if self.terminal is not None:
            self.terminal.info = FakeAccountInfo(login=OTHER_LOGIN, balance=55_555.0)
        return result


def _worker(
    settings: CollectorSettings,
    api: FakeApi,
    *,
    state_file: Path | None = None,
    known_offset: int | None = 120,
    now: Any = None,
) -> AccountWorker:
    """Цикл с подделками.

    По умолчанию смещение уже подтверждено прошлым запуском — так выглядит счёт, который
    хоть раз синхронизировался. `known_offset=None` — счёт, поднятый впервые: первый тик
    у него уходит на сверку часов брокера, и батч уезжает только со второго.
    """
    if state_file is None and known_offset is not None:
        state_file = settings.state_dir / "known-offset.json"
        state.write_state(state_file, state.WorkerState(server_utc_offset_minutes=known_offset))
    return AccountWorker(
        account_id=ACCOUNT_ID,
        settings=settings,
        api=api,
        clock=now or (lambda: NOW),
        state_file=state_file,
    )


def _terminal(**overrides: Any) -> FakeTerminal:
    kwargs: dict[str, Any] = {"tick_time": BROKER_TICK}
    kwargs.update(overrides)
    return FakeTerminal(**kwargs)


def _tick(
    worker: AccountWorker, terminal: FakeTerminal, assignment: Assignment | None = None
) -> Report:
    return worker.tick(
        terminal,
        assignment=assignment or assignment_for(),
        info=terminal.info,
    )


# --------------------------------------------------------------------------------------
# Счастливый путь
# --------------------------------------------------------------------------------------


def test_a_pass_sends_the_history_it_found(settings: CollectorSettings) -> None:
    api = FakeApi()
    terminal = _terminal(deals=[deal(ticket=1, at=200), deal(ticket=2, at=100)])
    report = _tick(_worker(settings, api), terminal)

    assert report.state == STATE_RUNNING
    assert report.terminal_login == LOGIN
    assert len(api.batches) == 1
    batch = api.batches[0]
    assert batch["account_id"] == ACCOUNT_ID
    assert batch["source"] == "collector"
    assert batch["server_utc_offset_minutes"] == 120
    assert [item["ticket"] for item in batch["deals"]] == [2, 1]


def test_the_batch_carries_no_login_or_server(settings: CollectorSettings) -> None:
    """Логин и сервер читаются, чтобы сверить счёт, а не чтобы уехать в контракт.

    Лишнее поле в теле — `400 validation_error` на весь батч: граница объявлена
    `extra="forbid"` (`S1-01`).
    """
    api = FakeApi()
    _tick(_worker(settings, api), _terminal(deals=[deal()]))
    batch = api.batches[0]
    assert "login" not in batch
    assert "server" not in batch
    assert set(batch["account_info"]) == {"currency", "margin_mode", "balance", "equity"}


def test_open_positions_ride_along_with_every_batch(settings: CollectorSettings) -> None:
    """Пустой список по контракту значит «открытых нет», а не «в этом батче не прислал»."""
    api = FakeApi()
    deals = [deal(ticket=number, at=100 + number) for number in range(1, 12_000)]
    terminal = _terminal(deals=deals, positions=[FakePosition(identifier=777)])
    _tick(_worker(settings, api), terminal)

    assert len(api.batches) == 3
    for batch in api.batches:
        assert [item["position_id"] for item in batch["open_positions"]] == [777]


def test_a_long_history_leaves_in_batches_of_five_thousand(settings: CollectorSettings) -> None:
    """SPEC.md 5.3: батч больше 5000 сделок сервер отвергает с 413."""
    api = FakeApi()
    deals = [deal(ticket=number, at=100 + number) for number in range(1, 10_002)]
    _tick(_worker(settings, api), _terminal(deals=deals))
    assert [len(batch["deals"]) for batch in api.batches] == [5000, 5000, 1]


def test_a_pass_with_nothing_to_send_still_reports_running(settings: CollectorSettings) -> None:
    api = FakeApi()
    worker = _worker(settings, api)
    terminal = _terminal(deals=[deal()])
    _tick(worker, terminal)
    report = _tick(worker, terminal)
    assert report.state == STATE_RUNNING
    assert len(api.batches) == 1


# --------------------------------------------------------------------------------------
# Сторож счёта — `X-66`
# --------------------------------------------------------------------------------------


def test_an_account_switched_mid_read_drops_the_batch(
    settings: CollectorSettings, monkeypatch: Any
) -> None:
    """Человек переключил счёт в терминале, пока тот отдавал историю.

    Без этой ветки сделки чужого счёта уехали бы в журнал нашего — молча и необратимо:
    `deals` append-only, а батч уже подписан нашим `account_id`.
    """
    recorder = _Recorder()
    monkeypatch.setattr(worker_module, "log", recorder)
    api = FakeApi()
    terminal = _terminal(
        deals=[deal()],
        info_after=FakeAccountInfo(login=999111, server=SERVER),
        switch_after=0,
    )
    report = _tick(_worker(settings, api), terminal)

    assert api.batches == []
    assert report.state == STATE_ERROR
    assert report.message == messages.ACCOUNT_SWITCHED
    assert recorder.find("collector.account_switched_mid_read")["open_login"] == 999111


def test_a_server_switched_mid_read_drops_the_batch_too(settings: CollectorSettings) -> None:
    """Тот же номер счёта на другом сервере — другой счёт, и это тот же отказ."""
    api = FakeApi()
    terminal = _terminal(
        deals=[deal()],
        info_after=FakeAccountInfo(login=LOGIN, server="Other-Broker-Demo"),
        switch_after=0,
    )
    report = _tick(_worker(settings, api), terminal)
    assert api.batches == []
    assert report.message == messages.ACCOUNT_SWITCHED


def test_the_same_account_after_the_read_sends_the_batch(settings: CollectorSettings) -> None:
    """Сторож не должен ломать обычный путь: тот же счёт — батч уезжает."""
    api = FakeApi()
    terminal = _terminal(
        deals=[deal()],
        info_after=FakeAccountInfo(login=LOGIN, server=SERVER.lower()),
        switch_after=0,
    )
    assert _tick(_worker(settings, api), terminal).state == STATE_RUNNING
    assert len(api.batches) == 1


def test_an_unreadable_second_answer_is_a_refusal_too(
    settings: CollectorSettings, monkeypatch: Any
) -> None:
    """Fail-closed: нечитаемый ответ — это «не доказано», а не «тот же счёт».

    Отказаться от батча из-за непонятного ответа стоит одного пропущенного окна: следующий
    тик заберёт его заново. Принять непонятный ответ за свой счёт стоит чужих сделок в
    журнале, и вынуть их обратно нечем (`identity.py`, `deals` append-only).
    """
    recorder = _Recorder()
    monkeypatch.setattr(worker_module, "log", recorder)
    api = FakeApi()
    terminal = _terminal(deals=[deal()], info_after=garbled_account_info(), switch_after=0)
    report = _tick(_worker(settings, api), terminal)

    assert api.batches == []
    assert report.state == STATE_ERROR
    assert report.message == messages.ACCOUNT_SWITCHED
    assert recorder.find("collector.account_switched_mid_read")["open_login"] is None


def test_the_guard_asks_the_terminal_a_second_time(settings: CollectorSettings) -> None:
    """Сверка обязана быть вторым **запросом**, а не повторным чтением того же снимка."""
    api = FakeApi()
    terminal = _terminal(deals=[deal()])
    _tick(_worker(settings, api), terminal)
    assert terminal.info_calls == 1  # первый снимок пришёл снаружи, этот — сторожа


def test_the_guard_stands_after_the_read_not_before_it(settings: CollectorSettings) -> None:
    """Смысл сторожа — его место: он отвечает, чей счёт **ответил**, а не чей мы спросили.

    Здесь счёт переключается внутри `history_deals()`, то есть ровно в том промежутке, ради
    которого сторож и написан. Сторож, переставленный до чтения истории, спросил бы терминал
    до щелчка, получил бы прежний счёт — и отправил бы чужие сделки в наш журнал.
    """
    api = FakeApi()
    terminal = _terminal(
        deals=[deal()],
        info_after=FakeAccountInfo(login=OTHER_LOGIN, server=SERVER),
        switch_during_history=True,
    )
    report = _tick(_worker(settings, api), terminal)

    assert terminal.switched_in_history  # подделка переключилась именно на чтении истории
    assert api.batches == []
    assert report.state == STATE_ERROR
    assert report.message == messages.ACCOUNT_SWITCHED


def test_a_switch_while_a_long_window_is_leaving_does_not_split_it(
    settings: CollectorSettings,
) -> None:
    """Окно — одно решение: доказали счёт один раз, и все чанки едут с тем же снимком.

    Переключение счёта посреди отправки безопасно по построению — `_send` в терминал не
    ходит вовсе, — но «по построению» держится ровно до первой правки. Окно, половина
    которого подписана одним снимком счёта, а половина другим, хуже отказа: отказ повторится
    следующим тиком, а разъехавшееся окно уже в журнале.
    """
    deals = [deal(ticket=number, at=100 + number) for number in range(1, 10_002)]
    terminal = _terminal(deals=deals)
    api = _ApiThatSwitchesTheTerminal(terminal=terminal)
    report = _tick(_worker(settings, api), terminal)

    assert report.state == STATE_RUNNING
    assert terminal.info.login == OTHER_LOGIN  # счёт сменился, пока окно ещё уезжало
    assert [len(batch["deals"]) for batch in api.batches] == [5000, 5000, 1]
    balances = {batch["account_info"]["balance"] for batch in api.batches}
    assert balances == {payload.decimal_text(FakeAccountInfo().balance)}


# --------------------------------------------------------------------------------------
# Окно выборки
# --------------------------------------------------------------------------------------


def test_window_is_asked_in_broker_hours(settings: CollectorSettings) -> None:
    """`history_deals_get` сравнивает границы с `deal.time`, а это часы брокера (SPEC.md 6.3)."""
    api = FakeApi()
    terminal = _terminal()
    _tick(_worker(settings, api), terminal)

    start, end = terminal.history_calls[0]
    assert start.tzinfo is None
    assert end == (NOW + timedelta(days=1, minutes=120)).replace(tzinfo=None)


def test_a_restart_asks_for_the_overlapping_window_again(settings: CollectorSettings) -> None:
    """Перекрытие окна намеренное: дубли снимает ингест по естественному ключу."""
    api = FakeApi()
    terminal = _terminal()
    last_sync = NOW - timedelta(hours=3)
    _tick(_worker(settings, api), terminal, assignment_for(last_sync_at=last_sync))

    start, _ = terminal.history_calls[0]
    assert start == (last_sync - timedelta(hours=24) + timedelta(minutes=120)).replace(tzinfo=None)


def test_sync_now_widens_the_window(settings: CollectorSettings) -> None:
    """Кнопка «синхронизировать сейчас» — 30 дней (SPEC.md 5.2)."""
    api = FakeApi()
    terminal = _terminal()
    _tick(
        _worker(settings, api),
        terminal,
        assignment_for(last_sync_at=NOW - timedelta(hours=1), sync_requested_at=NOW),
    )
    start, _ = terminal.history_calls[0]
    assert start == (NOW - timedelta(days=30) + timedelta(minutes=120)).replace(tzinfo=None)


def test_a_clock_behind_the_server_does_not_turn_the_window_inside_out(
    settings: CollectorSettings, monkeypatch: Any
) -> None:
    """`last_sync_at` из будущего иначе давал бы `start > end` и вечно пустой синк."""
    recorder = _Recorder()
    monkeypatch.setattr(worker_module, "log", recorder)
    api = FakeApi()
    terminal = _terminal()
    _tick(_worker(settings, api), terminal, assignment_for(last_sync_at=NOW + timedelta(days=1)))

    start, end = terminal.history_calls[0]
    assert start < end
    assert recorder.has("collector.clock_behind_server")


# --------------------------------------------------------------------------------------
# Когда молчать
# --------------------------------------------------------------------------------------


def test_a_new_deal_breaks_the_silence(settings: CollectorSettings) -> None:
    api = FakeApi()
    worker = _worker(settings, api)
    terminal = _terminal(deals=[deal(ticket=1)])
    _tick(worker, terminal)
    terminal.deals.append(deal(ticket=2, at=300))
    _tick(worker, terminal)
    assert len(api.batches) == 2


def test_a_closed_position_breaks_the_silence(settings: CollectorSettings) -> None:
    api = FakeApi()
    worker = _worker(settings, api)
    terminal = _terminal(deals=[deal()], positions=[FakePosition(identifier=5)])
    _tick(worker, terminal)
    terminal.positions.clear()
    _tick(worker, terminal)
    assert len(api.batches) == 2
    assert api.batches[-1]["open_positions"] == []


# --------------------------------------------------------------------------------------
# Отказы, которые человек обязан прочитать
# --------------------------------------------------------------------------------------


def test_non_usd_account_stops_instead_of_syncing(settings: CollectorSettings) -> None:
    """SPEC.md 8.2: синк не выполняется вовсе, и причина названа валютой."""
    api = FakeApi()
    terminal = _terminal(info=FakeAccountInfo(currency="EUR"), deals=[deal()])
    report = _tick(_worker(settings, api), terminal)

    assert api.batches == []
    assert report.state == STATE_ERROR
    assert "EUR" in str(report.message)


def test_a_refused_batch_is_reported_and_retried_next_tick(settings: CollectorSettings) -> None:
    api = FakeApi(refuse=ApiError("Счёт в архиве", code="account_archived", status=409))
    terminal = _terminal(deals=[deal()])
    worker = _worker(settings, api)
    report = _tick(worker, terminal)

    assert report.state == STATE_ERROR
    assert "Счёт в архиве" in str(report.message)
    # Ничего не запомнили: следующий тик обязан отправить то же окно заново.
    api.refuse = None
    assert _tick(worker, terminal).state == STATE_RUNNING
    assert len(api.batches) == 1


def test_a_deal_the_server_would_refuse_does_not_stop_the_account(
    settings: CollectorSettings,
) -> None:
    """Батч отвергается целиком, и одна испорченная сделка остановила бы счёт навсегда."""
    api = FakeApi()
    terminal = _terminal(deals=[deal(ticket=1), deal(ticket=2, at=300, symbol="EUR USD")])
    report = _tick(_worker(settings, api), terminal)

    assert [item["ticket"] for item in api.batches[0]["deals"]] == [1]
    assert report.state == STATE_RUNNING
    assert "2" in str(report.message)


def test_an_open_position_the_server_would_refuse_does_not_stop_the_account(
    settings: CollectorSettings,
) -> None:
    api = FakeApi()
    terminal = _terminal(
        deals=[deal()],
        positions=[FakePosition(identifier=1), FakePosition(identifier=2, type=7)],
    )
    report = _tick(_worker(settings, api), terminal)

    assert [item["position_id"] for item in api.batches[0]["open_positions"]] == [1]
    assert "позиция 2" in str(report.message)


def test_an_untranslatable_account_info_stops_with_words_instead_of_a_traceback(
    settings: CollectorSettings,
) -> None:
    """Неизвестный `margin_mode` — не повод уронить процесс: причина уходит на карточку."""
    api = FakeApi()
    terminal = _terminal(info=FakeAccountInfo(margin_mode=9), deals=[deal()])
    report = _tick(_worker(settings, api), terminal)

    assert api.batches == []
    assert report.state == STATE_ERROR
    assert str(report.message).startswith("Коллектор не смог собрать батч")


def test_a_terminal_error_escapes_to_the_owner_of_the_terminal(
    settings: CollectorSettings,
) -> None:
    """Терминалом владеет `main.py`, он и решает, что делать с обрывом."""
    api = FakeApi()
    terminal = _terminal(history_errors=[TerminalError(messages.TERMINAL_LOST, code=-10004)])
    with pytest.raises(TerminalError):
        _tick(_worker(settings, api), terminal)


# --------------------------------------------------------------------------------------
# Смещение часов брокера
# --------------------------------------------------------------------------------------


def test_no_quote_means_no_batch_and_a_readable_reason(settings: CollectorSettings) -> None:
    """Смещение обязательно в каждом батче: без него отправлять нечего (SPEC.md 6.3)."""
    api = FakeApi()
    terminal = _terminal(tick_time=None, deals=[deal()])
    report = _tick(_worker(settings, api, known_offset=None), terminal)

    assert api.batches == []
    assert report.state == STATE_ERROR
    assert report.message == messages.OFFSET_UNKNOWN


def test_the_first_offset_waits_for_a_second_quote(settings: CollectorSettings) -> None:
    """Первое значение не принимается: протухшая котировка испортила бы время всем сделкам."""
    api = FakeApi()
    worker = _worker(settings, api, known_offset=None)
    terminal = _terminal(deals=[deal()])

    first = _tick(worker, terminal)
    assert api.batches == []
    assert first.state == STATE_RUNNING
    assert first.message == messages.OFFSET_PENDING

    assert _tick(worker, terminal).state == STATE_RUNNING
    assert api.batches[0]["server_utc_offset_minutes"] == 120


def test_a_frozen_quote_is_not_a_second_opinion(settings: CollectorSettings) -> None:
    """У застывшей котировки `tick.time` не меняется, и повтор ничего не доказывает."""
    api = FakeApi()
    worker = _worker(settings, api, known_offset=None)
    terminal = _terminal(tick_step=0, deals=[deal()])

    _tick(worker, terminal)
    report = _tick(worker, terminal)
    assert api.batches == []
    assert report.message == messages.OFFSET_UNKNOWN


def test_a_remembered_offset_carries_a_closed_market(settings: CollectorSettings) -> None:
    """Перезапуск в субботу иначе означал бы простой до открытия рынка."""
    api = FakeApi()
    terminal = _terminal(tick_time=None, deals=[deal()])
    report = _tick(_worker(settings, api, known_offset=180), terminal)

    assert report.state == STATE_RUNNING
    assert api.batches[0]["server_utc_offset_minutes"] == 180


def test_a_confirmed_offset_is_written_down(settings: CollectorSettings) -> None:
    api = FakeApi()
    path = settings.state_dir / "offset.json"
    worker = _worker(settings, api, state_file=path, known_offset=None)
    terminal = _terminal(deals=[deal()])

    _tick(worker, terminal)
    assert state.read_state(path) == state.EMPTY
    _tick(worker, terminal)
    assert state.read_state(path).server_utc_offset_minutes == 120


def test_a_refused_candidate_leaves_a_line_in_the_log(
    settings: CollectorSettings, monkeypatch: Any
) -> None:
    """Молча выброшенный кандидат — тишина, в которой причину искать нечем."""
    recorder = _Recorder()
    monkeypatch.setattr(worker_module, "log", recorder)
    api = FakeApi()
    # Смещение известно, а котировка даёт скачок больше перевода часов.
    terminal = _terminal(tick_time=int((NOW + timedelta(hours=9)).timestamp()), deals=[deal()])
    _tick(_worker(settings, api, known_offset=120), terminal)

    assert recorder.find("collector.offset_rejected")["status"] == "jump_refused"


def test_a_clock_that_is_hours_off_says_so_instead_of_blaming_the_market(
    settings: CollectorSettings,
) -> None:
    """Расхождение больше любой зоны — это часы машины, а не закрытый рынок."""
    api = FakeApi()
    terminal = _terminal(tick_time=int((NOW + timedelta(hours=30)).timestamp()), deals=[deal()])
    report = _tick(_worker(settings, api, known_offset=None), terminal)

    assert api.batches == []
    assert "часы" in str(report.message).casefold()


def test_a_failing_server_time_is_logged_with_the_mt5_code(
    settings: CollectorSettings, monkeypatch: Any
) -> None:
    """X-67: код и описание от библиотеки обязаны быть в файле лога."""
    recorder = _Recorder()
    monkeypatch.setattr(worker_module, "log", recorder)

    class _NoTick(FakeTerminal):
        def server_time(self) -> int | None:
            raise TerminalError(messages.TERMINAL_LOST, code=-10004, description="IPC failed")

    api = FakeApi()
    report = _tick(_worker(settings, api, known_offset=None), _NoTick(deals=[deal()]))

    fields = recorder.find("collector.server_time_failed")
    assert fields["mt5_code"] == -10004
    assert fields["mt5_description"] == "IPC failed"
    assert report.state == STATE_ERROR


# --------------------------------------------------------------------------------------
# Тикеты не обязаны быть монотонными
# --------------------------------------------------------------------------------------


def test_a_deal_out_of_ticket_order_still_counts_as_new(settings: CollectorSettings) -> None:
    """«Новее последнего тикета» считается по максимуму, а не по хвосту хронологии.

    Монотонность тикетов MT5 нам никто не обещал; сделка с большим тикетом и более ранним
    временем иначе не разбудила бы отправку и повисла бы до keepalive.
    """
    api = FakeApi()
    worker = _worker(settings, api)
    terminal = _terminal(deals=[deal(ticket=10, at=1_788_400_000)])
    _tick(worker, terminal)
    terminal.deals.append(deal(ticket=99, at=1_788_100_000))
    _tick(worker, terminal)
    assert len(api.batches) == 2
