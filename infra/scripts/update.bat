@echo off
rem TradeDesk — обновление до свежего релиза на Windows (SPEC.md 11.3, ADR-0005).
rem См. комментарий в backup.bat: логика в update.sh, здесь только вызов и пауза.
setlocal

where bash >nul 2>nul
if errorlevel 1 goto :nobash

bash "%~dp0update.sh" %*
set RC=%errorlevel%
goto :done

:nobash
echo Не найден bash. Поставь Git for Windows — https://git-scm.com/download/win
set RC=1

:done
rem Без паузы окно закроется вместе с отчётом об обновлении — и вместе с отказом по
rem MASTER_KEY, который человек обязан прочитать.
if not "%TD_NO_PAUSE%"=="1" pause
exit /b %RC%
