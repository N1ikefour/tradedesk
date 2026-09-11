@echo off
rem TradeDesk — восстановление базы из бэкапа на Windows (SPEC.md 11.3).
rem См. комментарий в backup.bat: логика в restore.sh, здесь только вызов и пауза.
rem
rem Путь к файлу приезжает сюда как есть — с обратными слэшами. Разбирает его restore.sh:
rem в Git Bash «\» разделителем каталогов не считается, и normalize там, а не тут.
setlocal

rem Где взять bash и почему это не `where bash` — в find-bash.bat (X-63).
rem Он же печатает отказ, если bash не нашёлся, — один текст на все обёртки.
call "%~dp0find-bash.bat" "%~nx0"
if errorlevel 1 goto :nobash

"%TD_BASH%" "%~dp0restore.sh" %*
set RC=%errorlevel%
goto :done

:nobash
set RC=1

:done
rem Без паузы окно закроется вместе с таблицей «что будет перезаписано» — ровно с тем,
rem ради чего эту команду и запускают.
if not "%TD_NO_PAUSE%"=="1" pause
exit /b %RC%
