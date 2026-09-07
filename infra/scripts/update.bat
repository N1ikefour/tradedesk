@echo off
rem TradeDesk — обновление до свежего релиза на Windows (SPEC.md 11.3, ADR-0005).
rem См. комментарий в backup.bat: логика в update.sh, здесь только вызов.
setlocal

where bash >nul 2>nul
if errorlevel 1 (
  echo Не найден bash. Поставь Git for Windows — https://git-scm.com/download/win
  exit /b 1
)

bash "%~dp0update.sh" %*
exit /b %errorlevel%
