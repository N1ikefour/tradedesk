"""То немногое в `mt5_client.py`, что проверяемо без Windows.

Модуль целиком запустить негде: `MetaTrader5` под macOS не существует. Проверяется здесь
то, что от библиотеки не зависит: подготовка портабельной папки (обычная работа с
файловой системой) и три решения, вынесенные из методов терминала в чистые функции —
выбор свежайшего тика, чтение `None` от `positions_get()` и рост истории.

Не выполняется в этом наборе ни разу и остаётся списком «требует Windows»: `connect`,
`history_deals`, `positions_get`, `server_time` и всё, что внутри них зовёт библиотеку.
Цикл ожидания истории проверен на подставном модуле — то есть проверена его логика, а не
поведение настоящего `history_deals_total`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from collector import messages, mt5_client
from collector.mt5_client import TerminalError

ACCOUNT = "0192f1d4-2c6a-7c3f-9d1e-2b6a8f4c1d55"


def _installed_terminal(root: Path) -> Path:
    """Похожая на правду установка MT5: бинарник, настройки, кэши, скрипты."""
    home = root / "MetaTrader 5"
    (home / "MQL5" / "Experts").mkdir(parents=True)
    (home / "config").mkdir()
    (home / "Bases" / "E-Global-Real").mkdir(parents=True)
    (home / "Logs").mkdir()
    exe = home / "terminal64.exe"
    exe.write_text("binary", encoding="utf-8")
    (home / "config" / "accounts.dat").write_text("saved credentials", encoding="utf-8")
    (home / "Bases" / "E-Global-Real" / "ticks.dat").write_text("x" * 1000, encoding="utf-8")
    (home / "MQL5" / "Experts" / "robot.ex5").write_text("robot", encoding="utf-8")
    return exe


def test_portable_copy_lands_where_the_spec_says(tmp_path: Path) -> None:
    """SPEC.md 8.1: `MT5_PORTABLE_ROOT\\<account_id>`, по папке на счёт."""
    exe = _installed_terminal(tmp_path)
    root = tmp_path / "td-terminals"
    target = mt5_client.prepare_portable_dir(exe, root, ACCOUNT)
    assert target == root / ACCOUNT / "terminal64.exe"
    assert target.exists()


def test_saved_credentials_of_the_source_terminal_are_not_copied(tmp_path: Path) -> None:
    """`config` несёт учётные данные исходной установки — им не место в папке счёта."""
    exe = _installed_terminal(tmp_path)
    root = tmp_path / "td-terminals"
    mt5_client.prepare_portable_dir(exe, root, ACCOUNT)
    assert not (root / ACCOUNT / "config").exists()


def test_quote_caches_are_not_copied(tmp_path: Path) -> None:
    """`Bases` у живого терминала весит гигабайты, а строится заново сам."""
    exe = _installed_terminal(tmp_path)
    root = tmp_path / "td-terminals"
    mt5_client.prepare_portable_dir(exe, root, ACCOUNT)
    assert not (root / ACCOUNT / "Bases").exists()
    assert not (root / ACCOUNT / "Logs").exists()


def test_what_the_terminal_needs_is_copied(tmp_path: Path) -> None:
    exe = _installed_terminal(tmp_path)
    root = tmp_path / "td-terminals"
    mt5_client.prepare_portable_dir(exe, root, ACCOUNT)
    assert (root / ACCOUNT / "MQL5" / "Experts" / "robot.ex5").exists()


def test_an_existing_copy_is_left_alone(tmp_path: Path) -> None:
    """Второй запуск не имеет права затирать настройки и кэш истории этого счёта."""
    exe = _installed_terminal(tmp_path)
    root = tmp_path / "td-terminals"
    mt5_client.prepare_portable_dir(exe, root, ACCOUNT)
    marker = root / ACCOUNT / "origin.txt"
    marker.write_text("настройки счёта", encoding="utf-8")

    mt5_client.prepare_portable_dir(exe, root, ACCOUNT)
    assert marker.read_text(encoding="utf-8") == "настройки счёта"


def test_two_accounts_get_two_terminals(tmp_path: Path) -> None:
    """Один терминал = один счёт (SPEC.md 8.2): библиотека держит одно соединение."""
    exe = _installed_terminal(tmp_path)
    root = tmp_path / "td-terminals"
    first = mt5_client.prepare_portable_dir(exe, root, ACCOUNT)
    second = mt5_client.prepare_portable_dir(exe, root, "0192f1d4-2c6a-7c3f-9d1e-2b6a8f4c1d99")
    assert first != second
    assert first.exists()
    assert second.exists()


def test_missing_terminal_says_which_setting_to_check(tmp_path: Path) -> None:
    with pytest.raises(TerminalError) as error:
        mt5_client.prepare_portable_dir(tmp_path / "nope.exe", tmp_path / "out", ACCOUNT)
    assert "MT5_TERMINAL_EXE" in error.value.message
    assert "nope.exe" in error.value.message


@pytest.mark.parametrize("name", ["config", "Config", "BASES", "logs", "Tester"])
def test_skip_list_ignores_case(name: str) -> None:
    """Windows не различает регистр в именах папок — список не должен зависеть от него."""
    assert mt5_client.skips_portable_entry(name)


@pytest.mark.parametrize("name", ["MQL5", "terminal64.exe", "Profiles"])
def test_skip_list_keeps_what_matters(name: str) -> None:
    assert not mt5_client.skips_portable_entry(name)


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
        super().__init__(
            credentials=mt5_client.Credentials(login=1, server="S", password="x" * 12),
            terminal_exe=Path("terminal64.exe"),
            portable_root=Path("root"),
            account_id=ACCOUNT,
            sleep=lambda _seconds: None,
        )
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
