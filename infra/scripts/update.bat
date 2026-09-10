@echo off
rem TradeDesk — обновление до свежего релиза на Windows (SPEC.md 11.3, ADR-0005).
rem См. комментарий в backup.bat: логика в update.sh, здесь только вызов и пауза.
setlocal

rem Где взять bash и почему это не `where bash` — в find-bash.bat (X-63).
rem Он же печатает отказ, если bash не нашёлся, — один текст на все обёртки.
call "%~dp0find-bash.bat" "%~nx0"
if errorlevel 1 goto :nobash

"%TD_BASH%" "%~dp0update.sh" %*
set RC=%errorlevel%
goto :done

:nobash
set RC=1

:done
rem Без паузы окно закроется вместе с отчётом об обновлении — и вместе с отказом по
rem MASTER_KEY, который человек обязан прочитать.
if not "%TD_NO_PAUSE%"=="1" pause
exit /b %RC%
