"""То немногое в `mt5_client.py`, что проверяемо без Windows.

Модуль целиком запустить негде: `MetaTrader5` под macOS не существует. Но подготовка
портабельной папки — обычная работа с файловой системой, и она проверяется здесь. Всё
остальное (`connect`, `history_deals`, `positions_get`, `server_time`, `wait_for_history`)
не выполняется в этом наборе ни разу и перечислено в итоге задачи списком «требует
Windows».
"""

from __future__ import annotations

from pathlib import Path

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


def test_the_module_imports_without_metatrader5() -> None:
    """Ключевое свойство раскладки: `worker.py` импортируется на машине разработки.

    Будь `import MetaTrader5` наверху файла, непроверяемым стал бы и цикл синхронизации
    вместе со всеми своими решениями — а он тут самое ценное, что вообще можно проверить.
    """
    with pytest.raises(TerminalError) as error:
        mt5_client.import_mt5()
    assert error.value.message == messages.MT5_PACKAGE_MISSING
