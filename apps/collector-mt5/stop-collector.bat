@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem TradeDesk — остановить коллектор MT5 целиком (S1-10).
rem
rem Это единственный способ остановки, после которого не остаётся процессов счетов.
rem «Снять задачу» в диспетчере задач и taskkill /F убивают менеджер, а его процессы
rem счетов переживают такую остановку, продолжают синхронизацию и при следующем старте
rem получают вторых (X-57, docs/mt5-assumptions.md, допущение 39). Здесь порядок
rem обратный: сначала задача Планировщика, потом менеджер, потом процессы счетов.
rem
rem Кодировка: UTF-8 без BOM, CRLF, chcp первой командой (X-55).

where powershell >nul 2>nul
if errorlevel 1 (
  echo ОШИБКА: не найден PowerShell. Остановить коллектор можно так: закройте окно,
  echo в котором он запущен, а если он работает из Планировщика — снимите задачу
  echo «TradeDesk Collector MT5» и проверьте в диспетчере задач, что процессов
  echo python.exe из папки установки не осталось.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-service.ps1" -Stop %*
set "TD_RC=%errorlevel%"
echo.
pause
exit /b %TD_RC%
