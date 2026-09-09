@echo off
rem TradeDesk — остановка локального окружения на Windows (SPEC.md 11.3).
rem См. комментарий в start.bat: логика в stop.sh, здесь только вызов и пауза.
setlocal

where bash >nul 2>nul
if errorlevel 1 goto :nobash

bash "%~dp0stop.sh"
set RC=%errorlevel%
goto :done

:nobash
echo Не найден bash. Поставь Git for Windows — https://git-scm.com/download/win
set RC=1

:done
rem Без паузы окно закроется вместе с ответом на единственный вопрос, ради которого эту
rem команду и запускают: остановилось ли — и уцелели ли данные. Тем же местом закрывается
rem отказ «Docker не отвечает», после которого не остановилось ничего (X-61).
if not "%TD_NO_PAUSE%"=="1" pause
exit /b %RC%
