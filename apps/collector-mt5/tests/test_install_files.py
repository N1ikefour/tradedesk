"""Файлы установки — S1-10. Проверяется то немногое, что проверяемо без Windows.

Запустить `.bat` и `.ps1` на машине разработки нечем, и это не оговорка, а условие
задачи. Но часть свойств этих файлов ломается молча и убивает установку целиком, а
проверить их можно чтением байтов и разбором текста:

1. **Кодировка.** Русская консоль Windows читает `.bat` в CP866. Файл в UTF-8 без
   `chcp 65001` первой командой даёт кракозябры вместо первого же сообщения (`X-55`).
   Windows PowerShell 5.1 читает `.ps1` без BOM как CP1251 — тот же результат.
2. **Переводы строк.** `cmd.exe` разбирает `.bat` построчно и на файлах с одними LF
   спотыкается о `goto` и блоки в скобках. Git на macOS хранит байты как есть, то есть
   единственная защита — проверка.
3. **Пути.** `MT5_PORTABLE_ROOT` и `LOG_DIR` не имеют права оказаться внутри профиля
   пользователя: у первого пользователя он кириллический (`X-43`), а под Планировщиком
   заданий рабочей папкой по умолчанию становится `C:\\Windows\\System32`.
4. **Смысл, разъезжающийся между файлами.** Коды выхода живут в трёх местах сразу —
   `collector/worker.py`, `run-collector.bat` и таблица в `install-service.ps1`, откуда
   их читает человек после отказа автозапуска. Разошедшийся текст не ломает ничего
   видимого: он просто уводит человека не туда. Ревью `S1-10` нашло там ровно это —
   код 2 был описан как «Планировщик не нашёл файл» вместо «ошибка в collector.env».
   То же и с порядком остановки: он единственный отличает прощание от расстрела.

`install-service.ps1` целиком проверить нечем — интерпретатора нет ни на машине
разработки, ни в CI. Поэтому здесь проверяется его текст: таблица кодов, порядок в
`Stop-Collector`, чтение лога и наличие обработчика на отказе Планировщика. Всё
остальное — `docs/collector-windows-checklist.md`, по нему идёт живой человек.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from collector import bootstrap
from collector import main as manager
from collector.main import EXIT_FAILURE
from collector.worker import EXIT_CONFIG, EXIT_OK, EXIT_PLATFORM

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[1]

BATCH_FILES = (
    "run-collector.bat",
    "install-service.bat",
    "stop-collector.bat",
    "status-collector.bat",
)
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


def _powershell_function(name: str) -> str:
    """Тело функции PowerShell по её имени — по балансу фигурных скобок."""
    text = _text("install-service.ps1")
    header = re.search(rf"^function {name}(\(.*?\))? \{{", text, re.M)
    assert header is not None, f"функции {name} в скрипте нет"
    start = header.end() - 1
    depth = 0
    for offset, char in enumerate(text[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : offset + 1]
    raise AssertionError(f"у функции {name} не закрыта скобка")


def _task_result_table() -> dict[str, str]:
    """Таблица `$TaskResultText` из `install-service.ps1`, ключ → текст для человека."""
    text = _text("install-service.ps1")
    block = re.search(r"\$TaskResultText = @\{(.*?)^\}", text, re.S | re.M)
    assert block is not None, "таблица кодов последнего запуска пропала из скрипта"
    return dict(re.findall(r"'(-?\d+)'\s*=\s*'([^']*)'", block.group(1)))


def _batch_exit_messages() -> dict[str, str]:
    """Что `run-collector.bat` печатает на каждый код выхода менеджера."""
    text = _text("run-collector.bat")
    said = {}
    for code, label in re.findall(r'if "%TD_RC%"=="(-?\d+)" goto :(\w+)', text):
        body = re.search(rf"^:{label}\r?$(.*?)^goto :done\r?$", text, re.S | re.M)
        assert body is not None, f"у метки {label} нет тела"
        said[code] = body.group(1)
    return said


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


def test_the_manager_is_told_where_its_settings_are() -> None:
    """Относительный путь к `collector.env` считался бы от текущей папки, а она чужая.

    Под Планировщиком рабочую папку задаёт задача, но менеджер запускают и руками, из
    произвольного окна cmd. От этого же пути менеджер отсчитывает файл-просьбу
    остановиться, который кладёт `Stop-Collector`, — разъедься они, и остановка
    молча превратилась бы в принудительную.
    """
    text = _text("run-collector.bat")

    assert '-m collector.main --env-file "%TD_HOME%collector.env"' in text


def test_service_mode_does_not_swallow_the_other_keys() -> None:
    """`--service --once` без этого молча превращался бы в бесконечный запуск."""
    text = _text("run-collector.bat")

    assert 'call "%TD_SELF%"%TD_ARGS%' in text


def test_every_exit_code_of_the_manager_is_explained_to_the_human() -> None:
    """Коды выхода живут в трёх файлах, и текст к ним человек читает в двух последних."""
    table = _task_result_table()
    said = _batch_exit_messages()

    for code in (EXIT_OK, EXIT_FAILURE, EXIT_CONFIG, EXIT_PLATFORM):
        assert str(code) in table, f"install-service.ps1 молчит о коде {code}"
        assert str(code) in said, f"run-collector.bat молчит о коде {code}"


def test_the_task_result_table_says_what_the_exit_code_really_means() -> None:
    """Ревью `S1-10`: код 2 был описан как «Планировщик не нашёл run-collector.bat».

    Это код выхода действия, а не Планировщика, и означает он ошибку в `collector.env`
    (`worker.EXIT_CONFIG`) — то есть самый частый отказ из всех: человек правит этот
    файл руками. Неверная подсказка отправляла его переустанавливать автозапуск, а
    настоящая причина лежала строкой ниже, в хвосте лога.
    """
    table = _task_result_table()
    said = _batch_exit_messages()

    for code, marker in ((EXIT_CONFIG, "collector.env"), (EXIT_PLATFORM, "Windows")):
        assert marker in table[str(code)], f"install-service.ps1 о коде {code}"
        assert marker in said[str(code)], f"run-collector.bat о коде {code}"
    assert "аварийно" in table[str(EXIT_FAILURE)]
    assert "аварийно" in said[str(EXIT_FAILURE)]


def test_the_windows_error_code_in_the_table_is_the_real_one() -> None:
    """`0x80070002` — «файл не найден». `0x80070001` — ERROR_INVALID_FUNCTION.

    Второй стоял в таблице вместо первого: ключ, который не совпадёт никогда, то есть
    мёртвая строка на месте объяснения.
    """
    table = _task_result_table()

    assert "не нашёл" in table["2147942402"]
    assert "2147942401" not in table


def test_an_unexpected_exit_code_is_still_explained() -> None:
    """После `stop-collector.bat` код выхода не совпадает ни с одним из четырёх.

    Это `TerminateProcess`, и раньше на него не печаталось ничего: пустая строка,
    `pause` — и человек остаётся с вопросом, что это было.
    """
    text = _text("run-collector.bat")
    fallback = text.split('if "%TD_RC%"=="3" goto :say_platform')[1].split("goto :done")[0]

    assert "echo" in fallback
    assert "%TD_RC%" in fallback


def test_the_stop_asks_the_manager_before_it_kills_him() -> None:
    """Порядок — это и есть разница между «остановлен» и «не на связи».

    `Stop-ScheduledTask` снимает дерево процессов задачи целиком, то есть убивает
    менеджер: спрошенный после неё уже некому услышать просьбу. А `Stop-Process -Force`
    не доводит менеджер до `_shutdown`, где он единственный раз шлёт `state=stopped`.
    """
    body = _powershell_function("Stop-Collector")

    assert body.index("Request-GracefulStop") < body.index("Stop-ScheduledTask")
    assert body.index("Stop-ScheduledTask") < body.index("Stop-Process")
    # Менеджер гасится раньше процессов счетов: живой поднял бы их обратно своим тиком.
    assert "@($managers) + @($workers)" in body


def test_the_stop_writes_the_file_the_manager_is_watching() -> None:
    """Имя файла живёт в двух языках сразу, и разъезд был бы молчаливым."""
    text = _text("install-service.ps1")

    assert f"'{manager.STOP_FLAG_NAME}'" in text


def test_the_stop_flag_lands_in_the_folder_the_manager_watches() -> None:
    """Имя файла закреплено, а каталог — нет, и разъезд был бы полностью молчаливым.

    Просьба выйти работает только если `stop-collector.bat` кладёт файл ровно туда, куда
    смотрит менеджер. Цепочка идёт через три языка: `.ps1` строит путь от `$Here`, `.bat`
    отдаёт менеджеру `--env-file "%TD_HOME%collector.env"` от `%~dp0`, а менеджер берёт
    каталог этого файла. Разойдись любое звено — `Request-GracefulStop` создаст файл,
    которого никто не ждёт, отчитается «менеджер успел попрощаться», и остановка молча
    выродится в принудительную: `state=stopped` не уйдёт, счета через пять минут покажут
    «коллектор не на связи». Ни один тест этого не поймал бы: имена совпадают, порядок
    вызовов верен, текст на экране правильный.
    """
    ps1 = _text("install-service.ps1")
    bat = _text("run-collector.bat")
    source = (PACKAGE_ROOT / "collector" / "main.py").read_text(encoding="utf-8")

    assert f"$StopFlag = Join-Path $Here '{manager.STOP_FLAG_NAME}'" in ps1
    assert 'set "TD_HOME=%~dp0"' in bat
    assert '--env-file "%TD_HOME%collector.env"' in bat
    assert "stop_flag=env_file.parent / STOP_FLAG_NAME" in source

    # `$Here` у `.ps1` и `%~dp0` у `.bat` — один каталог только пока файлы лежат рядом.
    assert (PACKAGE_ROOT / "install-service.ps1").parent == (PACKAGE_ROOT / "run-collector.bat").parent


def test_the_forced_stop_says_what_it_costs() -> None:
    """`SPEC.md` §8.2: о принудительной остановке TradeDesk не узнаёт.

    Обещать мягкую остановку на Windows нельзя — гарантировать её нечем. Значит,
    человек обязан прочитать, что именно получилось, и почему счета через пять минут
    уедут в «коллектор не на связи» после его же осознанного действия.
    """
    body = _powershell_function("Stop-Collector")

    assert "принудительно" in body
    assert "не на связи" in body


def test_the_log_tail_is_read_without_guessing_the_code_page() -> None:
    """`Get-Content` без `-Encoding` в Windows PowerShell 5.1 — это CP1251.

    `run-collector.log` пишет cmd.exe после `chcp 65001`, то есть UTF-8 без BOM, и
    хвост этого файла — первое, куда смотрит человек, когда коллектор не поднялся.
    Назначить UTF-8 тоже мало: под Планировщиком консоли у задачи может не быть вовсе.
    """
    status = _powershell_function("Show-Status")
    reader = _powershell_function("Read-TextFile")

    assert "Get-Content" not in status
    assert "Read-TextLines $RunLog" in status
    # Строгий UTF-8 — тот, что бросает исключение на не-UTF-8, а не молча подставляет «?».
    assert "UTF8Encoding($false, $true)" in reader
    assert "OEMCP" in reader


def test_a_refusal_from_the_scheduler_is_caught_and_explained() -> None:
    """«Планировщик отказал» — отдельный сценарий тикета, а не сырой английский текст."""
    body = _powershell_function("Install-Task")

    assert body.index("try {") < body.index("Register-ScheduledTask")
    assert body.index("Register-ScheduledTask") < body.index("} catch {")
    assert "Планировщик заданий отказался завести задачу." in body


@pytest.mark.parametrize("name", INSTALL_FILES)
def test_install_files_ship_in_the_release_archive(name: str) -> None:
    """Файл, которого нет в `REQUIRED`, однажды уедет из архива незамеченным."""
    script = REPO_ROOT / "infra" / "scripts" / "make-release.sh"
    if not script.exists():
        pytest.skip("тесты гоняются вне репозитория — проверять состав архива нечем")

    assert f"apps/collector-mt5/{name}" in script.read_text(encoding="utf-8")
