@echo off
rem TradeDesk — запуск локального окружения на Windows (SPEC.md 11.3).
rem Логика одна на все платформы и живёт в start.sh: дублировать её на cmd означало бы
rem чинить каждую правку дважды. Здесь только вызов через bash из Git for Windows.
setlocal

where bash >nul 2>nul
if errorlevel 1 (
  echo Не найден bash. Поставь Git for Windows — https://git-scm.com/download/win
  echo Он нужен и для make init, и для запуска.
  exit /b 1
)

bash "%~dp0start.sh"
exit /b %errorlevel%
