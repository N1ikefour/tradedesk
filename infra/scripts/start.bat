@echo off
rem TradeDesk — запуск локального окружения на Windows (SPEC.md 11.3).
rem Логика одна на все платформы и живёт в start.sh: дублировать её на cmd означало бы
rem чинить каждую правку дважды. Здесь только вызов через bash из Git for Windows и пауза.
setlocal

where bash >nul 2>nul
if errorlevel 1 goto :nobash

bash "%~dp0start.sh"
set RC=%errorlevel%
goto :done

:nobash
echo Не найден bash. Поставь Git for Windows — https://git-scm.com/download/win
echo Он нужен и для make init, и для запуска.
set RC=1

:done
rem Пауза безусловная — та же, что в backup.bat, и по более сильному поводу. Окно,
rem открытое двойным щелчком, закрывается вместе с последними строками вывода, а у
rem запуска это адреса, по которым открывать приложение, и подсказка «SETUP.md, раздел
rem «Если запуск упал»», если он не поднялся. Паузить только по ненулевому коду значило
rem бы выбросить ровно то, ради чего запуск и делают: адреса печатаются при УСПЕХЕ
rem (X-61). Код возврата сохранён до паузы, чтобы наружу ушёл код start.sh. Для вызова
rem из другого скрипта паузу снимает TD_NO_PAUSE=1.
if not "%TD_NO_PAUSE%"=="1" pause
exit /b %RC%
