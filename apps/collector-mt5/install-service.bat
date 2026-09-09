@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem TradeDesk — поставить коллектор MT5 на автозапуск (S1-10). Двойной клик по этому
rem файлу делает то же, что install-service.ps1: вся логика там, здесь только вызов.
rem PowerShell вызывается с -ExecutionPolicy Bypass для одного запуска — политика
rem запуска скриптов на машине от этого не меняется.
rem
rem Кодировка: UTF-8 без BOM, CRLF, chcp первой командой — иначе русский текст ниже
rem превращается в кракозябры на консоли CP866 (X-55).

where powershell >nul 2>nul
if errorlevel 1 (
  echo ОШИБКА: не найден PowerShell. Он входит в Windows; если его нет, автозапуск
  echo придётся настроить руками через Планировщик заданий — см.
  echo docs\collector-windows-checklist.md.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-service.ps1" %*
set "TD_RC=%errorlevel%"
echo.
pause
exit /b %TD_RC%
