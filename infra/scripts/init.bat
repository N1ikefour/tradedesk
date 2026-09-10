@echo off
rem TradeDesk — создание .env на Windows (SPEC.md 11.2).
rem См. комментарий в backup.bat: логика в init-env.sh, здесь только вызов и пауза.
rem
rem Зачем файл вообще нужен. Запуск и остановка на Windows делаются двойным щелчком, а
rem самый первый шаг — создание .env — до этого требовал зайти в Git Bash. Барьер стоял
rem ровно там, где человек ещё ничего не получил взамен (X-17). Git Bash остаётся нужен
rem как зависимость: init-env.sh генерирует секреты его openssl. Заходить в него — нет.
setlocal

rem Где взять bash и почему это не `where bash` — в find-bash.bat (X-63).
rem Он же печатает отказ, если bash не нашёлся, — один текст на все обёртки.
call "%~dp0find-bash.bat" "%~nx0"
if errorlevel 1 goto :nobash

"%TD_BASH%" "%~dp0init-env.sh" %*
set RC=%errorlevel%
goto :done

:nobash
set RC=1

:done
rem Без паузы окно закроется вместе с предупреждением про MASTER_KEY — а это ключ от
rem паролей брокерских счетов, и человек обязан прочитать про него до того, как закроет
rem окно. Тем же местом закрывается и отказ перезаписать существующий .env.
if not "%TD_NO_PAUSE%"=="1" pause
exit /b %RC%
