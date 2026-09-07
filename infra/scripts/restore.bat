@echo off
rem TradeDesk — восстановление базы из бэкапа на Windows (SPEC.md 11.3).
rem См. комментарий в backup.bat: логика в restore.sh, здесь только вызов.
setlocal

where bash >nul 2>nul
if errorlevel 1 (
  echo Не найден bash. Поставь Git for Windows — https://git-scm.com/download/win
  exit /b 1
)

bash "%~dp0restore.sh" %*
exit /b %errorlevel%
