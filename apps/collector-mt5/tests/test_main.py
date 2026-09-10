"""Коллектор целиком на подделках — SPEC.md 8.2, пункт 1.

Здесь проверяется то, что появилось в `X-66`: подключение к **уже открытому** терминалу,
опознание счёта, который в нём открыт, и heartbeat за все счета сразу. Терминала на машине
разработки нет, поэтому проверяются решения, а не библиотека.

Главное свойство, ради которого написана половина файла: **счёт, которого нет в терминале,
не синхронизируется, и человек об этом читает словами.** Ошибка здесь не падает — она
кладёт сделки в чужой журнал.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from collector import identity, messages, state
from collector import main as main_module
from collector.api_client import ApiError
from collector.config import CollectorSettings
from collector.main import Collector, build_parser
from collector.mt5_client import TerminalError
from tests.conftest import (
    ACCOUNT_ID,
    LOGIN,
    OTHER_ACCOUNT_ID,
    SERVER,
    FakeAccountInfo,
    FakeApi,
    FakeTerminal,
    assignment_for,
    deal,
)

OTHER_LOGIN = 7654321


class _Recorder:
    """Подставной логгер: проверяется не формат строки, а сам факт, что она есть."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def _record(self, event: str, **fields: Any) -> None:
        self.events.append((event, fields))

    debug = info = warning = error = exception = _record

    def find(self, event: str) -> dict[str, Any]:
        return next(fields for name, fields in self.events if name == event)

    def count(self, event: str) -> int:
        return sum(1 for name, _ in self.events if name == event)

    def has(self, event: str) -> bool:
        return self.count(event) > 0


def _collector(
    settings: CollectorSettings,
    api: FakeApi,
    terminal: FakeTerminal | None = None,
    *,
    stop_flag: Path | None = None,
    known_offset: int | None = None,
) -> tuple[Collector, list[float]]:
    """Коллектор с подделками и список того, сколько он спал.

    `known_offset` — смещение часов брокера, уже подтверждённое прошлым запуском: так
    выглядит счёт, который хоть раз синхронизировался, и только на нём виден весь путь до
    батча. Без него первый тик уходит на сверку часов (`sync.resolve_offset`).
    """
    if known_offset is not None:
        for item in api.items:
            state.write_state(
                state.state_path(settings.state_dir, item.account_id),
                state.WorkerState(server_utc_offset_minutes=known_offset),
            )
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)

    def monotonic() -> float:
        # Часы идут ровно на столько, сколько коллектор спал: так тесты видят настоящие
        # интервалы, а не «прошло ноль секунд между тиками».
        return sum(slept)

    return Collector(
        settings=settings,
        api=api,
        terminal_factory=lambda: terminal,  # type: ignore[return-value,arg-type]
        sleep=sleep,
        monotonic=monotonic,
        stop_flag=stop_flag,
    ), slept


def _ready(**overrides: Any) -> FakeTerminal:
    kwargs: dict[str, Any] = {"tick_time": None, "deals": [deal()]}
    kwargs.update(overrides)
    return FakeTerminal(**kwargs)


# --------------------------------------------------------------------------------------
# Один открытый счёт — обычный день
# --------------------------------------------------------------------------------------


def test_the_open_account_is_the_one_that_syncs(settings: CollectorSettings) -> None:
    """Смещения нет (котировки нет), но путь до счёта пройден и heartbeat ушёл."""
    api = FakeApi(items=[assignment_for()])
    collector, _ = _collector(settings, api, _ready())
    assert collector.run(max_ticks=1) == main_module.EXIT_OK

    said = api.said(ACCOUNT_ID)
    assert said is not None
    assert said.state == "stopped"  # прощальный heartbeat `_shutdown`
    running = api.beats[0][0]
    assert running.account_id == ACCOUNT_ID


def test_a_second_account_waits_without_being_painted_as_broken(
    settings: CollectorSettings,
) -> None:
    """Ждущий счёт получает `running` без сообщения — это штатное состояние новой схемы.

    `state=error` — единственный способ написать текст на карточку, и он же красит её в
    «требует внимания». Три карточки из четырёх, вечно требующие внимания, сделали бы этот
    статус нечитаемым; чем счёт занят на самом деле, видно по `last_sync_at`.
    """
    api = FakeApi(
        items=[
            assignment_for(),
            assignment_for(OTHER_ACCOUNT_ID, login=OTHER_LOGIN, server=SERVER),
        ]
    )
    _collector(settings, api, _ready(tick_time=None))[0].run(max_ticks=1)

    waiting = api.beats[0][1]
    assert waiting.account_id == OTHER_ACCOUNT_ID
    assert waiting.state == "running"
    assert waiting.message is None


def test_the_terminal_account_is_logged_once_not_every_tick(
    settings: CollectorSettings, monkeypatch: Any
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(main_module, "log", recorder)
    api = FakeApi(items=[assignment_for()])
    _collector(settings, api, _ready())[0].run(max_ticks=3)

    assert recorder.count("collector.terminal_account") == 1
    assert recorder.find("collector.terminal_account")["login"] == LOGIN


# --------------------------------------------------------------------------------------
# Сторож счёта — `X-66`, самое важное в задаче
# --------------------------------------------------------------------------------------


def test_an_unknown_account_in_the_terminal_stops_everything_with_words(
    settings: CollectorSettings,
) -> None:
    """Терминал открыт, коллектор жив, а сделок не будет: об этом обязан быть текст.

    Без него человек видит два работающих окна и ждёт синхронизации, которой нет.
    """
    api = FakeApi(items=[assignment_for()])
    terminal = _ready(info=FakeAccountInfo(login=999111, server="Someone-Else"))
    _collector(settings, api, terminal)[0].run(max_ticks=1)

    said = api.beats[0][0]
    assert said.state == "error"
    assert "999111" in str(said.message)
    assert "Someone-Else" in str(said.message)
    assert api.batches == []


def test_a_login_match_on_another_server_refuses_and_names_both(
    settings: CollectorSettings, monkeypatch: Any
) -> None:
    """Номера демо-счетов у брокеров пересекаются: сервер обязателен, но причина адресная."""
    recorder = _Recorder()
    monkeypatch.setattr(main_module, "log", recorder)
    api = FakeApi(
        items=[
            assignment_for(),
            assignment_for(OTHER_ACCOUNT_ID, login=OTHER_LOGIN, server=SERVER),
        ]
    )
    terminal = _ready(info=FakeAccountInfo(login=LOGIN, server="Other-Broker-Demo"))
    _collector(settings, api, terminal)[0].run(max_ticks=1)

    guilty, innocent = api.beats[0]
    assert guilty.account_id == ACCOUNT_ID
    assert guilty.state == "error"
    assert "Other-Broker-Demo" in str(guilty.message)
    assert SERVER in str(guilty.message)
    assert innocent.state == "running"
    assert innocent.message is None
    assert api.batches == []
    assert recorder.find("collector.server_mismatch")["expected_server"] == SERVER


def test_the_server_name_is_compared_without_case(settings: CollectorSettings) -> None:
    """Имя сервера человек списывает глазами, и регистр не должен стоить ему синка."""
    api = FakeApi(items=[assignment_for(server="e-global-real")])
    terminal = _ready(info=FakeAccountInfo(server="E-Global-Real"), tick_time=1_788_357_791)
    _collector(settings, api, terminal, known_offset=120)[0].run(max_ticks=1)

    said = api.beats[0][0]
    assert said.state == "running"
    assert said.terminal_login == LOGIN
    assert len(api.batches) == 1


# --------------------------------------------------------------------------------------
# Терминал не открыт
# --------------------------------------------------------------------------------------


def test_a_closed_terminal_tells_every_account_to_open_it(
    settings: CollectorSettings, monkeypatch: Any
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(main_module, "log", recorder)
    api = FakeApi(items=[assignment_for(), assignment_for(OTHER_ACCOUNT_ID, login=OTHER_LOGIN)])
    terminal = _ready(
        connect_errors=[
            TerminalError(messages.TERMINAL_NOT_OPEN, code=-10005, description="IPC timeout")
        ]
    )
    _collector(settings, api, terminal)[0].run(max_ticks=1)

    for said in api.beats[0]:
        assert said.state == "error"
        assert said.message == messages.TERMINAL_NOT_OPEN
    fields = recorder.find("collector.connect_failed")
    assert fields["mt5_code"] == -10005
    assert fields["mt5_description"] == "IPC timeout"


def test_the_retry_is_the_next_tick_and_nothing_slower(settings: CollectorSettings) -> None:
    """Отказ означает «человек ещё не открыл терминал», и ждать четверть часа после того,
    как он его открыл, — худший из возможных ответов (до `X-66` было именно так)."""
    api = FakeApi(items=[assignment_for()])
    terminal = _ready(
        connect_errors=[TerminalError(messages.TERMINAL_NOT_OPEN, code=-10005)],
    )
    collector, slept = _collector(settings, api, terminal)
    collector.run(max_ticks=2)

    assert terminal.connected == 2
    # Пауза между тиками — обычный интервал heartbeat, без всякого удвоения.
    assert sum(slept) == pytest.approx(float(settings.heartbeat_interval_seconds))


def test_a_terminal_lost_mid_work_is_reconnected_next_tick(
    settings: CollectorSettings, monkeypatch: Any
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(main_module, "log", recorder)
    api = FakeApi(items=[assignment_for()])
    terminal = _ready(
        info_errors=[TerminalError(messages.TERMINAL_LOST, code=-10004, description="IPC")]
    )
    collector, _ = _collector(settings, api, terminal)
    collector.run(max_ticks=2)

    assert api.beats[0][0].message == messages.TERMINAL_LOST
    assert terminal.closed >= 1
    assert terminal.connected == 2
    assert recorder.find("collector.terminal_lost")["mt5_code"] == -10004


# --------------------------------------------------------------------------------------
# Задания
# --------------------------------------------------------------------------------------


def test_no_accounts_at_all_says_so_in_the_log_only(
    settings: CollectorSettings, monkeypatch: Any
) -> None:
    """Отправить heartbeat не за кого, и единственный канал — файл лога."""
    recorder = _Recorder()
    monkeypatch.setattr(main_module, "log", recorder)
    api = FakeApi(items=[])
    _collector(settings, api, _ready())[0].run(max_ticks=1)

    assert api.heartbeats == []
    assert recorder.find("collector.no_assignments")["reason"] == messages.NO_ASSIGNMENTS


def test_api_silence_keeps_the_accounts_it_already_knows(
    settings: CollectorSettings, monkeypatch: Any
) -> None:
    """Одна неудачная минута не имеет права снять счета с наблюдения."""
    recorder = _Recorder()
    monkeypatch.setattr(main_module, "log", recorder)
    api = FakeApi(items=[assignment_for()])
    collector, _ = _collector(settings, api, _ready())
    collector.run(max_ticks=1)

    api.assignments_error = ApiError("нет связи", code="", status=0)
    collector._watched = (assignment_for(),)
    collector._tick()

    assert recorder.find("collector.assignments_unavailable")["reason"] == "нет связи"
    assert collector._watched


def test_a_paused_account_is_forgotten(settings: CollectorSettings, monkeypatch: Any) -> None:
    """Возвращённый из паузы счёт обязан взять `last_sync_at` с сервера, а не из головы."""
    recorder = _Recorder()
    monkeypatch.setattr(main_module, "log", recorder)
    api = FakeApi(items=[assignment_for(), assignment_for(OTHER_ACCOUNT_ID, login=OTHER_LOGIN)])
    collector, _ = _collector(settings, api, _ready())
    collector._tick()
    assert set(collector._workers) == {ACCOUNT_ID}

    api.items = [assignment_for(OTHER_ACCOUNT_ID, login=OTHER_LOGIN)]
    collector._tick()
    assert collector._workers == {}
    assert recorder.find("collector.account_released")["account_id"] == ACCOUNT_ID


# --------------------------------------------------------------------------------------
# Heartbeat и остановка
# --------------------------------------------------------------------------------------


def test_heartbeat_failure_does_not_stop_the_loop(
    settings: CollectorSettings, monkeypatch: Any
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(main_module, "log", recorder)
    api = FakeApi(
        items=[assignment_for()],
        heartbeat_error=ApiError("нет связи", code="", status=503),
    )
    assert _collector(settings, api, _ready())[0].run(max_ticks=2) == main_module.EXIT_OK
    assert recorder.find("collector.heartbeat_failed")["status"] == 503


def test_a_normal_stop_releases_the_terminal_and_says_stopped(
    settings: CollectorSettings,
) -> None:
    """`state=stopped` статуса счёта не меняет: коллектор остановил человек."""
    api = FakeApi(items=[assignment_for()])
    terminal = _ready()
    _collector(settings, api, terminal)[0].run(max_ticks=1)

    assert terminal.closed >= 1
    last = api.beats[-1][0]
    assert last.state == "stopped"
    assert last.message == messages.STOPPED


def test_a_crash_reaches_the_account_card(settings: CollectorSettings) -> None:
    """Единственный случай, когда о счёте рассказать буквально некому, кроме heartbeat."""
    api = FakeApi(items=[assignment_for()])
    collector, _ = _collector(settings, api, _ready())

    def explode() -> None:
        raise RuntimeError("boom")

    collector._reports = explode  # type: ignore[assignment,method-assign]
    with pytest.raises(RuntimeError):
        collector.run(max_ticks=1)

    last = api.beats[-1][0]
    assert last.state == "error"
    assert "RuntimeError" in str(last.message)


def test_the_stop_flag_takes_the_collector_through_a_normal_shutdown(
    settings: CollectorSettings, tmp_path: Path
) -> None:
    """Сигнал чужому процессу на Windows не доставить — просьба приходит файлом."""
    flag = tmp_path / main_module.STOP_FLAG_NAME
    api = FakeApi(items=[assignment_for()])
    collector, _ = _collector(settings, api, _ready(), stop_flag=flag)

    def sleep(_seconds: float) -> None:
        flag.write_text("stop", encoding="utf-8")

    collector.sleep = sleep
    assert collector.run(max_ticks=0) == main_module.EXIT_OK
    assert not flag.exists()
    assert api.beats[-1][0].state == "stopped"


def test_a_flag_left_from_the_last_time_does_not_stop_the_new_run(
    settings: CollectorSettings, tmp_path: Path
) -> None:
    flag = tmp_path / main_module.STOP_FLAG_NAME
    flag.write_text("stop", encoding="utf-8")
    api = FakeApi(items=[assignment_for()])
    collector, _ = _collector(settings, api, _ready(), stop_flag=flag)
    assert collector.run(max_ticks=1) == main_module.EXIT_OK
    # Тик состоялся: heartbeat тика плюс прощальный. Прочитанная чужая просьба дала бы
    # выход до первого тика, а значит и ни одного heartbeat.
    assert len(api.beats) == 2


def test_without_a_flag_path_the_collector_does_not_look_for_one(
    settings: CollectorSettings,
) -> None:
    api = FakeApi(items=[assignment_for()])
    collector, _ = _collector(settings, api, _ready(), stop_flag=None)
    assert not collector._stop_requested()
    assert collector.run(max_ticks=1) == main_module.EXIT_OK


def test_the_pause_between_ticks_is_the_heartbeat_interval(settings: CollectorSettings) -> None:
    api = FakeApi(items=[assignment_for()])
    collector, slept = _collector(settings, api, _ready())
    collector.run(max_ticks=2)
    assert sum(slept) == pytest.approx(float(settings.heartbeat_interval_seconds))


def test_both_intervals_of_the_env_file_still_mean_something(
    settings: CollectorSettings,
) -> None:
    """Цикл один, а интервала в `collector.env` два — и оба обязаны на что-то влиять.

    Взять один и забыть второй значило бы оставить в файле, который человек правит руками,
    поле-обманку. Поэтому тик идёт по меньшему из двух, а терминал спрашивается не чаще,
    чем велит `SYNC_INTERVAL_SECONDS`: heartbeat при этом уходит каждый тик, иначе
    `check_collectors` через пять минут молчания увёл бы счёт в «не на связи» (`SPEC.md` §10).
    """
    rare = settings.model_copy(
        update={"sync_interval_seconds": 300, "heartbeat_interval_seconds": 60}
    )
    api = FakeApi(
        items=[
            assignment_for(),
            assignment_for(OTHER_ACCOUNT_ID, login=OTHER_LOGIN, server=SERVER),
        ]
    )
    terminal = _ready(tick_time=1_788_357_791)
    collector, slept = _collector(rare, api, terminal, known_offset=120)
    collector.run(max_ticks=5)

    assert slept == [1.0] * 240  # четыре паузы по 60 с, порезанные на секунды
    # Пять тиков — пять heartbeat'ов плюс прощальный, а терминал спрошен один раз.
    assert len(api.beats) == 6
    assert len(api.batches) == 1
    assert len(terminal.history_calls) == 1
    # Тики без синка молчат: причину на карточке ставит только сам синк.
    assert [beat[0].message for beat in api.beats[1:5]] == [None] * 4


def test_a_tick_without_a_sync_still_reports_every_account(
    settings: CollectorSettings,
) -> None:
    """Тик без синка обязан отметиться **за все** счета, а не только за открытый.

    Иначе ждущий счёт молчит `SYNC_INTERVAL_SECONDS`, и `check_collectors` через пять минут
    молчания уводит его в «коллектор не на связи» (`SPEC.md` §10) — то есть в поломку,
    которой нет. Ради этого в `collector.env` и живут два интервала, а не один.
    """
    rare = settings.model_copy(
        update={"sync_interval_seconds": 300, "heartbeat_interval_seconds": 60}
    )
    api = FakeApi(
        items=[
            assignment_for(),
            assignment_for(OTHER_ACCOUNT_ID, login=OTHER_LOGIN, server=SERVER),
        ]
    )
    collector, _ = _collector(rare, api, _ready(tick_time=1_788_357_791), known_offset=120)
    collector.run(max_ticks=3)

    for beat in api.beats:
        assert {item.account_id for item in beat} == {ACCOUNT_ID, OTHER_ACCOUNT_ID}
    # Открытый счёт назван и на тиках без синка: сервер по нему сверяет, куда смотрит терминал.
    quiet = {item.account_id: item for item in api.beats[1]}
    assert quiet[ACCOUNT_ID].terminal_login == LOGIN
    assert quiet[OTHER_ACCOUNT_ID].terminal_login is None


def test_two_cards_for_one_open_account_stop_everything(
    settings: CollectorSettings, monkeypatch: Any
) -> None:
    """Два подошедших счёта — отказ, а не «побеждает первый в ответе сервера».

    Уникальность в БД сравнивает имя сервера посимвольно, а коллектор — без регистра, так
    что «E-Global-Real» и «e-global-real» с одним логином заводятся оба. Взять первый
    значило бы, что журнал, в который лягут сделки, выбирает порядок выдачи assignments.
    """
    recorder = _Recorder()
    monkeypatch.setattr(main_module, "log", recorder)
    api = FakeApi(
        items=[
            assignment_for(server=SERVER),
            assignment_for(OTHER_ACCOUNT_ID, server=SERVER.lower()),
        ]
    )
    collector, _ = _collector(settings, api, _ready(), known_offset=120)
    collector.run(max_ticks=1)

    assert api.batches == []
    for said in api.beats[0]:
        assert said.state == "error"
        assert str(LOGIN) in str(said.message)
    assert recorder.find("collector.ambiguous_account")["open_login"] == LOGIN


def test_a_non_numeric_login_refuses_instead_of_crashing(settings: CollectorSettings) -> None:
    """Библиотека обещает число, и обещание непроверяемое: терминала на macOS нет.

    Краш процесса здесь стоил бы краш-петли под Планировщиком без единой строки на карточке,
    хотя соседний непереводимый `margin_mode` давно превращается в текст.
    """
    api = FakeApi(items=[assignment_for()])
    terminal = _ready(info=FakeAccountInfo(login="293272"))  # type: ignore[arg-type]
    collector, _ = _collector(settings, api, terminal, known_offset=120)
    assert collector.run(max_ticks=1) == main_module.EXIT_OK

    assert api.batches == []
    assert api.beats[0][0].message == messages.ACCOUNT_UNREADABLE


def test_the_history_is_given_time_to_load_after_connecting(
    settings: CollectorSettings,
) -> None:
    """`SPEC.md` §8.3: после подключения ждать, пока история не перестанет расти.

    Без этого первый батч после каждого переподключения уезжает неполным — не потеря
    (вставка идемпотентна), но журнал счёта неполон до следующего тика.
    """
    api = FakeApi(items=[assignment_for()])
    terminal = _ready()
    collector, _ = _collector(settings, api, terminal)
    collector.run(max_ticks=3)

    # Один раз на подключение, а не на тик: ждать по 30 с каждую минуту незачем.
    assert terminal.waited == 1


# --------------------------------------------------------------------------------------
# Точка входа
# --------------------------------------------------------------------------------------


def test_the_collector_refuses_to_run_outside_windows(monkeypatch: Any) -> None:
    monkeypatch.setattr(main_module, "platform_refusal", lambda: "не Windows")
    assert main_module.main([]) == main_module.EXIT_PLATFORM


def test_parser_takes_an_env_file_and_a_single_tick() -> None:
    args = build_parser().parse_args(["--env-file", "x.env", "--once"])
    assert args.env_file == Path("x.env")
    assert args.once is True


def test_a_bad_env_file_exits_with_the_documented_code(tmp_path: Path, monkeypatch: Any) -> None:
    """Код 2 — тот, что `run-collector.bat` и Планировщик переводят в «ошибка в collector.env»."""
    monkeypatch.setattr(main_module, "platform_refusal", lambda: None)
    env = tmp_path / "collector.env"
    env.write_text("API_URL=localhost:8000\nCOLLECTOR_TOKEN=x\nCOLLECTOR_ID=a\n", encoding="utf-8")
    assert main_module.main(["--env-file", str(env)]) == main_module.EXIT_CONFIG


def test_every_match_status_ends_in_a_decision() -> None:
    """Перечень статусов закрытый, и каждый обязан превращаться в действие коллектора.

    Новый статус, забытый в `_reports`, означал бы счёт, о котором коллектор промолчал не
    по решению, а по недосмотру.
    """
    from typing import get_args

    assert set(get_args(identity.MatchStatus)) == {
        "match",
        "server_mismatch",
        "ambiguous",
        "unknown_account",
    }
