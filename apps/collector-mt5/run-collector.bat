@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem TradeDesk — коллектор MT5: подготовка окружения и запуск (SPEC.md 8.2 п.4, S1-10).
rem
rem Кодировка файла: UTF-8 без BOM, переводы строк CRLF, первая команда — chcp 65001.
rem Русская консоль Windows читает .bat в CP866, и без chcp весь текст ниже стал бы
rem кракозябрами (X-55). PYTHONUTF8 — та же беда со стороны Python: без него print()
rem русской строки в консоли CP866 падает с UnicodeEncodeError, а structlog заваливает
rem экран сообщениями «--- Logging error ---» вместо строк лога.
rem
rem Режимы:
rem   run-collector.bat             запуск коллектора; остановка — Ctrl+C или stop-collector.bat
rem   run-collector.bat --once      один проход: проверить настройки и связь с TradeDesk
rem   run-collector.bat --reinstall переустановить зависимости и выйти
rem   run-collector.bat --service   запуск из Планировщика заданий: вывод в logs\run-collector.log
rem
rem Переменные окружения (нужны только нам, человеку — нет):
rem   TD_PYTHON             команда запуска Python вместо поиска 3.12 (без пробелов в пути)
rem   TD_ALLOW_ANY_PYTHON   разрешить непроверенную версию Python 3.13+

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "TD_HOME=%~dp0"
set "TD_LOGDIR=%TD_HOME%logs"
set "TD_VENV=%TD_HOME%.venv"
set "TD_VENV_PY=%TD_VENV%\Scripts\python.exe"
set "TD_STAMP=%TD_VENV%\.installed-pyproject.toml"
set "TD_PY_WANTED=3.12"
set "TD_RC=0"

cd /d "%TD_HOME%"
if errorlevel 1 (
  echo Не удалось перейти в папку установки: %TD_HOME%
  exit /b 1
)

rem Планировщик заданий запускает задачу без консоли: всё, что коллектор напечатает при
rem старте, иначе уходит в никуда, и «задача выполнена с кодом 2» выглядит как успех.
rem Метка, а не блок в скобках: %errorlevel% внутри блока подставляется при разборе, то
rem есть до вызова, и код возврата задачи всегда оказывался бы нулём.
if /i "%~1"=="--service" goto :service

echo.
echo ==== TradeDesk: коллектор MT5 ====
echo %date% %time%
echo Папка установки: %TD_HOME%

rem Путь установки вне латиницы: отсюда запускается Python, отсюда же он порождает
rem процессы счетов и сюда пишет логи. На таких путях мы это не проверяли (X-43, X-54).
echo "%TD_HOME%"| findstr /r /c:"[^ -~]" >nul
if not errorlevel 1 (
  echo.
  echo ОШИБКА: в пути установки есть буквы вне латиницы.
  echo Перенесите папку установки в корень диска — например, в C:\tradedesk — и
  echo запустите этот файл оттуда. Терминал MetaTrader 5 и Python на таких путях
  echo ведут себя непредсказуемо, а разбираться в этом придётся вам одному.
  goto :fail
)

rem ---------------------------------------------------------------------------
rem Python. Версия названа явно: пакет требует 3.12+, но проверен только на 3.12
rem (.python-version, гейт CI). На 3.13 и 3.14 коллектор не гонял никто.
rem ---------------------------------------------------------------------------

set "PY="
if defined TD_PYTHON goto :py_explicit

py -%TD_PY_WANTED% -c "import sys" >nul 2>nul
if not errorlevel 1 (
  set "PY=py -%TD_PY_WANTED%"
  goto :py_found
)

python -c "import sys; sys.exit(0 if sys.version[:4] == '3.12' else 1)" >nul 2>nul
if not errorlevel 1 (
  set "PY=python"
  goto :py_found
)

if defined TD_ALLOW_ANY_PYTHON goto :py_any
goto :no_python

:py_explicit
set "PY=%TD_PYTHON%"
goto :py_found

:py_any
python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 12) else 1)" >nul 2>nul
if errorlevel 1 goto :no_python
set "PY=python"
echo.
echo ВНИМАНИЕ: TD_ALLOW_ANY_PYTHON — коллектор пойдёт на версии Python, которую
echo никто не проверял. Странности после этого — не баг коллектора, а эта строка.

:py_found
%PY% -c "import sys; print('Python', sys.version.split()[0], 'из', sys.executable)"
if errorlevel 1 goto :no_python

rem ---------------------------------------------------------------------------
rem Виртуальное окружение. Оно же чинит кириллицу в пути к самому Python: процессы
rem счетов порождаются через sys.executable, а в .venv это ASCII-путь установки,
rem а не C:\Users\<имя кириллицей>\... (X-43).
rem ---------------------------------------------------------------------------

if not exist "%TD_VENV_PY%" (
  echo.
  echo Создаю виртуальное окружение .venv ...
  %PY% -m venv "%TD_VENV%"
  if errorlevel 1 (
    echo.
    echo ОШИБКА: не удалось создать .venv. Проверьте, что папка установки не
    echo «только для чтения» и что на диске есть место, и запустите файл снова.
    goto :fail
  )
)

"%TD_VENV_PY%" -c "import sys" >nul 2>nul
if errorlevel 1 (
  echo.
  echo ОШИБКА: виртуальное окружение .venv сломано — обычно это значит, что
  echo Python, которым его создавали, удалили или обновили. Удалите папку
  echo %TD_VENV%
  echo и запустите этот файл снова.
  goto :fail
)

rem ---------------------------------------------------------------------------
rem Зависимости. Ставятся при первом запуске и после обновления продукта; в обычный
rem день pip не зовётся вовсе — иначе автозапуск после перезагрузки зависел бы от
rem интернета и от доступности PyPI.
rem ---------------------------------------------------------------------------

set "TD_INSTALL="
set "TD_ONLY_INSTALL="
if /i "%~1"=="--reinstall" (
  set "TD_INSTALL=1"
  set "TD_ONLY_INSTALL=1"
)
if not exist "%TD_STAMP%" set "TD_INSTALL=1"
if not defined TD_INSTALL (
  fc /b "%TD_HOME%pyproject.toml" "%TD_STAMP%" >nul 2>nul
  if errorlevel 1 set "TD_INSTALL=1"
)

if defined TD_INSTALL (
  echo.
  echo Устанавливаю библиотеки коллектора — нужен интернет, обычно это 1-2 минуты ...
  "%TD_VENV_PY%" -m pip install --disable-pip-version-check -e ".[mt5]"
  if errorlevel 1 (
    echo.
    echo ОШИБКА: не удалось установить библиотеки. Чаще всего причина одна из двух:
    echo   нет интернета — проверьте связь и запустите файл снова;
    echo   антивирус или прокси не пускают pip — попробуйте ещё раз позже.
    goto :fail
  )
  copy /y "%TD_HOME%pyproject.toml" "%TD_STAMP%" >nul
)

if defined TD_ONLY_INSTALL (
  echo.
  echo Библиотеки переустановлены. Запустите run-collector.bat без ключей.
  goto :done
)

rem ---------------------------------------------------------------------------
rem Настройки. COLLECTOR_TOKEN переносится из .env установки, чтобы человек не
rem копировал секрет глазами; остальное — его решение, и о нём модуль скажет сам.
rem ---------------------------------------------------------------------------

"%TD_VENV_PY%" -m collector.bootstrap --env-file "%TD_HOME%collector.env" --example "%TD_HOME%collector.env.example" --app-env "%TD_HOME%..\..\.env"
if errorlevel 1 goto :fail_quiet

rem ---------------------------------------------------------------------------
rem Запуск
rem ---------------------------------------------------------------------------

echo.
echo Коллектор запущен. Это окно закрывать нельзя — в нём он и работает.
echo Остановить: Ctrl+C здесь или файл stop-collector.bat.
echo Что происходит со счетами, видно в TradeDesk на экране «Счета».
echo.

"%TD_VENV_PY%" -m collector.main %*
set "TD_RC=%errorlevel%"

echo.
if "%TD_RC%"=="0" echo Коллектор остановлен.
if "%TD_RC%"=="1" echo Коллектор аварийно остановился. Подробности — logs\collector.log.
if "%TD_RC%"=="2" echo Ошибка в collector.env — текст выше называет строку.
if "%TD_RC%"=="3" echo Коллектор работает только на Windows.
goto :done

:no_python
echo.
echo ОШИБКА: не найден Python %TD_PY_WANTED%.
echo.
echo Коллектор проверен только на Python %TD_PY_WANTED% — на нём же собирается весь
echo TradeDesk. Версия посвежее с python.org скорее всего заработает, но проверить
echo это на вашей машине будет некому, поэтому запускаться на ней мы не будем.
echo.
echo Что сделать:
echo   1. Откройте https://www.python.org/downloads/windows/
echo   2. Скачайте «Windows installer (64-bit)» из раздела Python 3.12.x
echo   3. При установке оставьте галочку «Install launcher for all users» —
echo      она и даёт команду py, которой этот файл ищет нужную версию
echo   4. Запустите run-collector.bat снова
echo.
echo Уже установленную у вас версию Python это не тронет: 3.12 встанет рядом,
echo а не поверх, и другие программы продолжат работать на своей.
goto :fail

:fail
echo.
:fail_quiet
if not defined TD_SERVICE pause
exit /b 1

:done
if not defined TD_SERVICE pause
exit /b %TD_RC%

rem Запуск из Планировщика: тот же файл, но весь вывод — в logs\run-collector.log.
rem Возврат кода наружу здесь единственный способ сказать Планировщику, что не вышло.
:service
if not exist "%TD_LOGDIR%" mkdir "%TD_LOGDIR%"
set "TD_RUNLOG=%TD_LOGDIR%\run-collector.log"
rem Сюда же уходит stderr менеджера, то есть все строки лога вторым экземпляром: своя
rem ротация есть у collector.log, а у этого файла её не было бы вовсе. Ротация грубая —
rem один старый файл на 5 МБ, потому что ценность у него одна: последний запуск.
if exist "%TD_RUNLOG%" for %%F in ("%TD_RUNLOG%") do if %%~zF GTR 5242880 move /y "%TD_RUNLOG%" "%TD_RUNLOG%.old" >nul
set "TD_SERVICE=1"
call "%~f0" >>"%TD_RUNLOG%" 2>&1
exit /b %errorlevel%
