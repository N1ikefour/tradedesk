@echo off
rem TradeDesk — резервная копия базы на Windows (SPEC.md 11.3).
rem Логика одна на все платформы и живёт в backup.sh: дублировать её на cmd означало бы
rem чинить каждую правку дважды, а расходятся такие пары молча. Здесь только вызов
rem через bash из Git for Windows и пауза в конце.
setlocal

where bash >nul 2>nul
if errorlevel 1 goto :nobash

bash "%~dp0backup.sh" %*
set RC=%errorlevel%
goto :done

:nobash
echo Не найден bash. Поставь Git for Windows — https://git-scm.com/download/win
set RC=1

:done
rem Окно, открытое двойным щелчком, закрывается вместе с последней строкой вывода — а это
rem путь к свежей копии. Пауза безусловная: определять способ запуска через %cmdcmdline%
rem мы бы не проверили ничем, а лишний Enter дешевле потерянного пути. Для вызова из
rem другого скрипта паузу снимает TD_NO_PAUSE=1.
if not "%TD_NO_PAUSE%"=="1" pause
exit /b %RC%
