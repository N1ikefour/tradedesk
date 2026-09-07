@echo off
rem TradeDesk — резервная копия базы на Windows (SPEC.md 11.3).
rem Логика одна на все платформы и живёт в backup.sh: дублировать её на cmd означало бы
rem чинить каждую правку дважды, а расходятся такие пары молча. Здесь только вызов
rem через bash из Git for Windows.
setlocal

where bash >nul 2>nul
if errorlevel 1 (
  echo Не найден bash. Поставь Git for Windows — https://git-scm.com/download/win
  exit /b 1
)

bash "%~dp0backup.sh" %*
exit /b %errorlevel%
