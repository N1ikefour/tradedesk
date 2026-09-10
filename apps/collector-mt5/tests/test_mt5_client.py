"""Обёртка над `MetaTrader5`: то немногое в ней, что вообще можно проверить без Windows.

Проверяются решения, вынесенные из непроверяемого слоя в чистые функции, и **форма вызова
`initialize`** — та самая, из-за которой коллектор не забрал ни одной сделки на первом
прогоне (`X-66`). Сам вызов библиотеки здесь не выполняется ни разу и выполниться не может.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from collector import messages, mt5_client
from collector.mt5_client import TerminalError

# --------------------------------------------------------------------------------------
# Подключение: чем именно коллектор зовёт библиотеку
# --------------------------------------------------------------------------------------


class _InitModule:
    """Ровно те вызовы, которые делает `connect`, и запись их аргументов."""

    def __init__(self, *, ok: bool = True, error: tuple[int, str] = (1, "Success")) -> None:
        self.ok = ok
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.shutdowns = 0

    def initialize(self, *args: Any, **kwargs: Any) -> bool:
        self.calls.append({"args": args, "kwargs": kwargs})
        return self.ok

    def last_error(self) -> tuple[int, str]:
        return self.error

    def shutdown(self) -> None:
        self.shutdowns += 1


def _terminal(monkeypatch: Any, module: _InitModule) -> mt5_client.Mt5Terminal:
    """Терминал с подменённой библиотекой: настоящей на macOS не существует."""
    monkeypatch.setattr(mt5_client, "import_mt5", lambda: module)
    return mt5_client.Mt5Terminal(sleep=lambda _seconds: None)


def test_connect_passes_neither_a_path_nor_credentials(monkeypatch: Any) -> None:
    """Главный вывод `X-66`, и он проверяется формой вызова, а не комментарием.

    `initialize(path=…, portable=True, login=…, password=…, server=…)` возвращал
    `(-10005, 'IPC timeout')` **всегда** — десятки попыток, четыре прогона, оба счёта. Тот
    же терминал в тот же момент отвечал `True` на `initialize()` без аргументов. Вернётся
    сюда `path` или `password` — коллектор снова перестанет забирать сделки, и заметить это
    можно будет только на Windows.
    """
    module = _InitModule()
    _terminal(monkeypatch, module).connect()
    assert len(module.calls) == 1
    call = module.calls[0]
    assert call["args"] == ()
    assert call["kwargs"] == {"timeout": mt5_client.INITIALIZE_TIMEOUT_MS}


def test_a_refused_connection_carries_the_numeric_code_for_the_log(monkeypatch: Any) -> None:
    """X-67: человеку — текст, в файл лога — код и описание от библиотеки."""
    module = _InitModule(ok=False, error=(-10005, "IPC timeout"))
    with pytest.raises(TerminalError) as raised:
        _terminal(monkeypatch, module).connect()
    assert raised.value.code == -10005
    assert raised.value.description == "IPC timeout"
    assert raised.value.message == messages.TERMINAL_NOT_OPEN
    assert "-10005" not in raised.value.message


def test_closing_releases_the_link_and_leaves_the_window_alone(monkeypatch: Any) -> None:
    """`shutdown()` рвёт только наш канал: терминал открыл человек, и закрывать его нельзя."""
    module = _InitModule()
    terminal = _terminal(monkeypatch, module)
    terminal.connect()
    terminal.close()
    assert module.shutdowns == 1
    assert terminal._mt5 is None


def test_using_a_closed_terminal_says_so_in_words() -> None:
    terminal = mt5_client.Mt5Terminal()
    with pytest.raises(TerminalError) as raised:
        terminal.account_info()
    assert raised.value.message == messages.TERMINAL_LOST


def test_no_trading_call_exists_in_the_module() -> None:
    """Права коллектора кончаются на чтении (`CLAUDE.md` §5), и это не только про пароль.

    Пароля у коллектора больше нет вовсе (`T-07`), но библиотека торгует не паролем, а
    вызовом: единственная защита — что таких вызовов в файле нет.
    """
    source = mt5_client.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    for forbidden in ("order_send", "order_check", "order_calc"):
        assert forbidden not in text, forbidden


# --------------------------------------------------------------------------------------
# Решения, вынесенные из непроверяемого слоя
# --------------------------------------------------------------------------------------


@dataclass
class _Tick:
    time: Any


def test_the_freshest_quote_wins_because_age_is_the_error_in_the_offset() -> None:
    """Смещение считается из тика, и возраст котировки — это прямая ошибка в нём."""
    ticks = [_Tick(1_788_357_000), _Tick(1_788_357_900), _Tick(1_788_356_000)]
    assert mt5_client.freshest_tick_time(ticks) == 1_788_357_900


@pytest.mark.parametrize(
    "ticks",
    [
        [None, None],
        [],
        [_Tick(0)],
        [_Tick(None)],
        [_Tick(-5)],
        [_Tick("вчера")],
    ],
)
def test_a_probe_without_a_quote_gives_nothing_instead_of_a_guess(ticks: list[Any]) -> None:
    """`symbol_info_tick` по неизвестному брокеру символу отдаёт `None`, а `time` бывает нулём.

    Ноль — это «тика нет», а не 1970 год: смещение из него получилось бы величиной в
    полвека, и лучше не отправить батч, чем отправить с выдуманным временем.
    """
    assert mt5_client.freshest_tick_time(ticks) is None


def test_empty_positions_are_told_apart_from_a_broken_link() -> None:
    """`positions_get()` отдаёт `None` и на пустом списке, и на отказе — различает код.

    Цена ошибки несимметрична: принять отказ за пустоту значит сказать серверу «открытых
    позиций нет» и потерять их все разом.
    """
    assert mt5_client.positions_mean_empty(messages.RES_S_OK)
    assert not mt5_client.positions_mean_empty(messages.RES_E_INTERNAL_FAIL_CONNECT)
    assert not mt5_client.positions_mean_empty(messages.RES_E_NOT_FOUND)


@pytest.mark.parametrize(
    ("total", "previous", "expected"),
    [
        (504, 504, "settled"),
        (504, 300, "growing"),
        (0, -1, "growing"),
        (None, 10, "unreadable"),
        (-1, 10, "unreadable"),
        ("504", 10, "unreadable"),
        (True, 10, "unreadable"),
    ],
)
def test_history_growth_is_read_the_same_way_every_time(
    total: Any, previous: int, expected: str
) -> None:
    assert mt5_client.history_step(total, previous) == expected


class _FakeModule:
    """Ровно те вызовы библиотеки, которые делает `wait_for_history`."""

    def __init__(self, totals: list[int]) -> None:
        self.totals = totals
        self.calls = 0

    def history_deals_total(self, start: Any, end: Any) -> int:
        self.calls += 1
        return self.totals[min(self.calls - 1, len(self.totals) - 1)]


class _TerminalWithModule(mt5_client.Mt5Terminal):
    """Терминал без терминала: подменён только модуль библиотеки."""

    def __init__(self, module: _FakeModule) -> None:
        super().__init__(sleep=lambda _seconds: None)
        self._fake = module

    def _module(self) -> Any:
        return self._fake


def test_waiting_stops_as_soon_as_history_stops_growing() -> None:
    module = _FakeModule([100, 504, 504])
    _TerminalWithModule(module).wait_for_history()
    assert module.calls == 3


def test_history_that_never_settles_says_so_instead_of_going_quiet(monkeypatch: Any) -> None:
    """Выход по таймауту при растущей истории — первый батч уедет неполным.

    Молчать здесь нельзя: понять постфактум, почему в журнале половина сделок, можно
    только по строке в логе — история к тому моменту уже догрузится.
    """
    recorded: list[tuple[str, dict[str, Any]]] = []

    class _Recorder:
        def warning(self, event: str, **fields: Any) -> None:
            recorded.append((event, fields))

    monkeypatch.setattr(mt5_client, "log", _Recorder())
    module = _FakeModule(list(range(1, 100)))
    _TerminalWithModule(module).wait_for_history()
    assert recorded and recorded[0][0] == "collector.history_still_loading"


def test_the_module_imports_without_metatrader5() -> None:
    """Ключевое свойство раскладки: `worker.py` импортируется на машине разработки.

    Будь `import MetaTrader5` наверху файла, непроверяемым стал бы и цикл синхронизации
    вместе со всеми своими решениями — а он тут самое ценное, что вообще можно проверить.
    """
    with pytest.raises(TerminalError) as error:
        mt5_client.import_mt5()
    assert error.value.message == messages.MT5_PACKAGE_MISSING
