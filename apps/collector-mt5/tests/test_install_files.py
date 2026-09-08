"""Файлы установки — S1-10. Проверяется то немногое, что проверяемо без Windows.

Запустить `.bat` и `.ps1` на машине разработки нечем, и это не оговорка, а условие
задачи. Но три свойства этих файлов ломаются молча и убивают установку целиком, а
проверить их можно чтением байтов:

1. **Кодировка.** Русская консоль Windows читает `.bat` в CP866. Файл в UTF-8 без
   `chcp 65001` первой командой даёт кракозябры вместо первого же сообщения (`X-55`).
   Windows PowerShell 5.1 читает `.ps1` без BOM как CP1251 — тот же результат.
2. **Переводы строк.** `cmd.exe` разбирает `.bat` построчно и на файлах с одними LF
   спотыкается о `goto` и блоки в скобках. Git на macOS хранит байты как есть, то есть
   единственная защита — проверка.
3. **Пути.** `MT5_PORTABLE_ROOT` и `LOG_DIR` не имеют права оказаться внутри профиля
   пользователя: у первого пользователя он кириллический (`X-43`), а под Планировщиком
   заданий рабочей папкой по умолчанию становится `C:\\Windows\\System32`.

Про сами сценарии установки — `docs/collector-windows-checklist.md`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from collector import bootstrap

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[1]

BATCH_FILES = ("run-collector.bat", "install-service.bat", "stop-collector.bat")
POWERSHELL_FILES = ("install-service.ps1",)
INSTALL_FILES = BATCH_FILES + POWERSHELL_FILES

UTF8_BOM = b"\xef\xbb\xbf"

# Переменные окружения Windows, ведущие внутрь профиля пользователя. Ни одна из них не
# имеет права попасть в пути коллектора: там кириллица (X-43) и «очистка диска».
PROFILE_VARIABLES = ("%USERPROFILE%", "%LOCALAPPDATA%", "%APPDATA%", "%HOMEPATH%")


def _bytes(name: str) -> bytes:
    return (PACKAGE_ROOT / name).read_bytes()


def _text(name: str) -> str:
    return _bytes(name).decode("utf-8-sig")


@pytest.mark.parametrize("name", INSTALL_FILES)
def test_install_files_are_utf8(name: str) -> None:
    _bytes(name).decode("utf-8-sig")


@pytest.mark.parametrize("name", INSTALL_FILES)
def test_install_files_use_windows_line_endings(name: str) -> None:
    raw = _bytes(name)
    assert b"\r\n" in raw
    assert raw.replace(b"\r\n", b"").count(b"\n") == 0, "есть строки только с LF"


@pytest.mark.parametrize("name", BATCH_FILES)
def test_batch_files_switch_the_console_to_utf8_first(name: str) -> None:
    """`chcp` обязан стоять до первой русской буквы, иначе она уже не прочтётся."""
    raw = _bytes(name)
    assert not raw.startswith(UTF8_BOM), "cmd.exe печатает BOM как «п»»ї» перед первой командой"
    lines = _text(name).splitlines()
    assert lines[0] == "@echo off"
    assert lines[1] == "chcp 65001 >nul"
    assert "\n".join(lines[:2]).isascii()


def test_the_collector_runs_with_python_in_utf8_mode() -> None:
    """Без `PYTHONUTF8` русский `print` падает в консоли CP866 с UnicodeEncodeError."""
    text = _text("run-collector.bat")
    assert 'set "PYTHONUTF8=1"' in text


@pytest.mark.parametrize("name", POWERSHELL_FILES)
def test_powershell_files_carry_a_bom(name: str) -> None:
    """Windows PowerShell 5.1 без BOM читает файл как CP1251 — русский текст рассыпается."""
    assert _bytes(name).startswith(UTF8_BOM)


@pytest.mark.parametrize("name", BATCH_FILES)
def test_batch_files_never_point_into_the_user_profile(name: str) -> None:
    """Проверяются `.bat`: они строят пути сами, из `%~dp0` и переменных Windows.

    `install-service.ps1` профиль упоминает намеренно — он сверяет с ним пути из
    `collector.env` и предупреждает человека, а не подставляет их.
    """
    text = _text(name)
    for variable in PROFILE_VARIABLES:
        assert variable not in text, f"{name}: путь из профиля пользователя"


@pytest.mark.parametrize("name", INSTALL_FILES)
def test_install_files_do_not_set_collector_paths(name: str) -> None:
    """`MT5_PORTABLE_ROOT` и `LOG_DIR` задаёт `collector.env`, и только он.

    Подстановка этих путей из скрипта вернула бы профиль пользователя через чёрный ход:
    скрипт знает `%~dp0` и переменные Windows, и обе дороги ведут туда.
    """
    text = _text(name)
    for key in ("MT5_PORTABLE_ROOT=", "LOG_DIR="):
        assert key not in text, f"{name}: {key} задаётся мимо collector.env"


def test_the_example_keeps_the_terminal_root_short_and_latin() -> None:
    values = bootstrap.parse_env((PACKAGE_ROOT / "collector.env.example").read_text("utf-8"))

    assert values["MT5_PORTABLE_ROOT"] == "C:\\td-terminals"
    assert values["MT5_PORTABLE_ROOT"].isascii()
    assert values["LOG_DIR"] == "logs"


def test_the_scheduled_task_sets_its_working_directory() -> None:
    """Без явной рабочей папки Планировщик стартует задачу из `C:\\Windows\\System32`.

    Относительный `LOG_DIR=logs` уехал бы туда, и первое, что человек увидел бы, —
    отсутствие логов там, где их велено искать.
    """
    text = _text("install-service.ps1")

    assert "-WorkingDirectory $Here" in text


def test_the_batch_calls_bootstrap_the_way_bootstrap_expects() -> None:
    """Ключи `.bat` и argparse живут в разных файлах и разъезжаются молча."""
    text = _text("run-collector.bat")
    options = {
        option
        for action in bootstrap.build_parser()._actions
        for option in action.option_strings
        if option != "-h" and option != "--help"
    }

    assert "-m collector.bootstrap" in text
    for option in options:
        assert f"{option} " in text


def test_the_manager_is_started_by_its_module_path() -> None:
    text = _text("run-collector.bat")

    assert "-m collector.main" in text


@pytest.mark.parametrize("name", INSTALL_FILES)
def test_install_files_ship_in_the_release_archive(name: str) -> None:
    """Файл, которого нет в `REQUIRED`, однажды уедет из архива незамеченным."""
    script = REPO_ROOT / "infra" / "scripts" / "make-release.sh"
    if not script.exists():
        pytest.skip("тесты гоняются вне репозитория — проверять состав архива нечем")

    assert f"apps/collector-mt5/{name}" in script.read_text(encoding="utf-8")
