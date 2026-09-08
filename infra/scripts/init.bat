@echo off
rem TradeDesk — создание .env на Windows (SPEC.md 11.2).
rem См. комментарий в backup.bat: логика в init-env.sh, здесь только вызов и пауза.
rem
rem Зачем файл вообще нужен. Запуск и остановка на Windows делаются двойным щелчком, а
rem самый первый шаг — создание .env — до этого требовал зайти в Git Bash. Барьер стоял
rem ровно там, где человек ещё ничего не получил взамен (X-17). Git Bash остаётся нужен
rem как зависимость: init-env.sh генерирует секреты его openssl. Заходить в него — нет.
setlocal

where bash >nul 2>nul
if errorlevel 1 goto :nobash

bash "%~dp0init-env.sh" %*
set RC=%errorlevel%
goto :done

:nobash
echo Не найден bash. Поставь Git for Windows — https://git-scm.com/download/win
echo Он нужен и для создания .env, и для запуска.
set RC=1

:done
rem Без паузы окно закроется вместе с предупреждением про MASTER_KEY — а это ключ от
rem паролей брокерских счетов, и человек обязан прочитать про него до того, как закроет
rem окно. Тем же местом закрывается и отказ перезаписать существующий .env.
if not "%TD_NO_PAUSE%"=="1" pause
exit /b %RC%
