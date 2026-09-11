@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem TradeDesk — что сейчас с коллектором MT5 (S1-10).
rem
rem Первое, что стоит открыть, когда счета в TradeDesk молчат: состояние задачи
rem Планировщика, число процессов коллектора, открыт ли терминал MetaTrader 5 и хвост
rem logs\run-collector.log. Вся логика —
rem в install-service.ps1 -Status, здесь только вызов, чтобы это работало двойным кликом:
rem человеку, у которого не поднялся коллектор, не до командной строки.
rem
rem Кодировка: UTF-8 без BOM, CRLF, chcp первой командой (X-55).

where powershell >nul 2>nul
if errorlevel 1 (
  echo ОШИБКА: не найден PowerShell. Посмотреть, что с коллектором, можно так: в
  echo диспетчере задач — процесс python.exe и terminal64.exe, в Планировщике
  echo заданий — задача «TradeDesk Collector MT5», в папке установки — файл
  echo logs\run-collector.log.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-service.ps1" -Status %*
set "TD_RC=%errorlevel%"
echo.
pause
exit /b %TD_RC%
