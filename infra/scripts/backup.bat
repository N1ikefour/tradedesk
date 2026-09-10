@echo off
rem TradeDesk — резервная копия базы на Windows (SPEC.md 11.3).
rem Логика одна на все платформы и живёт в backup.sh: дублировать её на cmd означало бы
rem чинить каждую правку дважды, а расходятся такие пары молча. Здесь только вызов
rem через bash из Git for Windows и пауза в конце.
setlocal

rem Где взять bash и почему это не `where bash` — в find-bash.bat (X-63).
rem Он же печатает отказ, если bash не нашёлся, — один текст на все обёртки.
call "%~dp0find-bash.bat" "%~nx0"
if errorlevel 1 goto :nobash

"%TD_BASH%" "%~dp0backup.sh" %*
set RC=%errorlevel%
goto :done

:nobash
set RC=1

:done
rem Окно, открытое двойным щелчком, закрывается вместе с последней строкой вывода — а это
rem путь к свежей копии. Пауза безусловная: определять способ запуска через %cmdcmdline%
rem мы бы не проверили ничем, а лишний Enter дешевле потерянного пути. Для вызова из
rem другого скрипта паузу снимает TD_NO_PAUSE=1.
if not "%TD_NO_PAUSE%"=="1" pause
exit /b %RC%
