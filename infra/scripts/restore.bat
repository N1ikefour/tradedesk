@echo off
rem TradeDesk — восстановление базы из бэкапа на Windows (SPEC.md 11.3).
rem См. комментарий в backup.bat: логика в restore.sh, здесь только вызов и пауза.
rem
rem Путь к файлу приезжает сюда как есть — с обратными слэшами. Разбирает его restore.sh:
rem в Git Bash «\» разделителем каталогов не считается, и normalize там, а не тут.
setlocal

where bash >nul 2>nul
if errorlevel 1 goto :nobash

bash "%~dp0restore.sh" %*
set RC=%errorlevel%
goto :done

:nobash
echo Не найден bash. Поставь Git for Windows — https://git-scm.com/download/win
set RC=1

:done
rem Без паузы окно закроется вместе с таблицей «что будет перезаписано» — ровно с тем,
rem ради чего эту команду и запускают.
if not "%TD_NO_PAUSE%"=="1" pause
exit /b %RC%
