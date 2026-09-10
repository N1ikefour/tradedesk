@echo off
chcp 65001 >nul
rem TradeDesk — поиск bash.exe из Git for Windows (X-63).
rem
rem ⚠️ Кодировка файла: UTF-8 БЕЗ BOM, переводы строк CRLF, `chcp 65001` первой командой.
rem Тот же рецепт, что у apps/collector-mt5/*.bat (S1-10), и по той же причине: русская
rem консоль Windows читает вывод в CP866, а ниже — двенадцать строк русского текста,
rem которые cmd печатает сам. Это единственный экран отказа всей установки: кракозябры
rem на нём обесценивают и список мест поиска, и подсказку про TD_BASH. BOM недопустим
rem отдельно — cmd.exe печатает его мусором перед первой командой. Всё это закреплено
rem проверкой байтов в infra/scripts/test-scripts.sh: запустить .bat на macOS нечем.
rem
rem Файл не для двойного щелчка: сам он ничего не запускает. Его зовут через `call`
rem остальные шесть .bat, и он отдаёт найденный путь в переменной TD_BASH. Код возврата 1
rem означает «не нашли»; сообщение об этом печатает он же — иначе шесть обёрток держали бы
rem шесть копий одного текста, а расходятся такие копии молча.
rem
rem ⚠️ setlocal здесь НЕТ намеренно: он стёр бы TD_BASH на выходе, и вызывающий .bat
rem получил бы пустоту. На chcp это не распространяется — кодовая страница принадлежит
rem консоли, а не окружению, и endlocal вызывающего её не откатывает.
rem
rem ⚠️ `where bash` не используется вовсе, и это не упущение. Измерено на живой Windows 10
rem 22H2 (сборка 19045.6332) 10 сентября 2026, на первом прогоне установки:
rem   * установщик Git с параметрами по умолчанию кладёт в PATH только Git\cmd, где лежит
rem     git.exe. bash.exe лежит в Git\bin — то есть `where bash` молчит на машине, где
rem     bash есть, и человек читает «поставь Git», уже поставив Git;
rem   * после установки WSL2 (он нужен Docker Desktop) в системе появляется
rem     C:\Windows\System32\bash.exe — запускалка подсистемы Linux, а не оболочка.
rem     `where bash` находит её первой, и запуск через неё падает с «WSL (10 - Relay)
rem     ERROR: CreateProcessCommon:818: execvpe(/bin/bash) failed: No such file or
rem     directory» — сообщением, которое ни про Git, ни про PATH не говорит ничего.
rem Дописать Git\bin в PATH второе не лечит в принципе: системный PATH просматривается
rem раньше пользовательского. Поэтому bash ищется по путям. PATH спрашивается ровно об
rem одном — о git.exe (четвёртая попытка ниже), и подмена git.exe чужой подсистемой нам
rem не грозит: System32\bash.exe там есть, а System32\git.exe нет.

rem Путь, заданный человеком руками, — первым: Git может стоять где угодно.
if defined TD_BASH if exist "%TD_BASH%" exit /b 0
set "TD_BASH="

if exist "%ProgramFiles%\Git\bin\bash.exe" set "TD_BASH=%ProgramFiles%\Git\bin\bash.exe"
if defined TD_BASH exit /b 0

rem Кавычки вокруг всего пути обязательны: в имени этой переменной есть скобки.
if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" set "TD_BASH=%ProgramFiles(x86)%\Git\bin\bash.exe"
if defined TD_BASH exit /b 0

rem Установка «только для меня»: её установщик Git предлагает, когда прав администратора нет.
if exist "%LOCALAPPDATA%\Programs\Git\bin\bash.exe" set "TD_BASH=%LOCALAPPDATA%\Programs\Git\bin\bash.exe"
if defined TD_BASH exit /b 0

rem Git в нестандартной папке. Сам git.exe в PATH есть — его туда кладёт установщик по
rem умолчанию, — а bash.exe лежит на два уровня выше рядом: Git\cmd\git.exe даёт
rem Git\bin\bash.exe. Так же сходится и Git\bin\git.exe.
rem %%~f приводит путь с «..» к нормальному виду, существования файла не требуя, — поэтому
rem результат обязательно проверяется через `if exist`: сборки Git, где git.exe лежит на
rem другой глубине (Git\mingw64\bin\git.exe), дадут путь к несуществующему файлу.
set "TD_GITEXE="
for %%I in (git.exe) do set "TD_GITEXE=%%~$PATH:I"
if defined TD_GITEXE for %%I in ("%TD_GITEXE%\..\..\bin\bash.exe") do set "TD_BASH=%%~fI"
if defined TD_BASH if exist "%TD_BASH%" exit /b 0
set "TD_BASH="

rem Имя вызвавшего .bat приезжает аргументом. При двойном щелчке по самому find-bash.bat
rem аргумента нет, и без замены строка ниже напечатала бы путь с пустым хвостом. init.bat —
rem шаг 3 SETUP.md, с него установка начинается.
set "TD_CALLER=%~1"
if not defined TD_CALLER set "TD_CALLER=init.bat"

echo Не найден bash.exe из Git for Windows. Без него не работает ни один шаг установки.
echo.
echo Искали здесь:
echo     %ProgramFiles%\Git\bin\bash.exe
echo     %ProgramFiles(x86)%\Git\bin\bash.exe
echo     %LOCALAPPDATA%\Programs\Git\bin\bash.exe
echo     ..\..\bin\bash.exe рядом с git.exe из PATH
echo.
echo Git не установлен — поставьте: https://git-scm.com/download/win
echo Git стоит в другой папке — назовите файл сами, в окне cmd:
echo     set TD_BASH=D:\Git\bin\bash.exe
echo     "%~dp0%TD_CALLER%"
echo.
echo Дописывать bash.exe в PATH бесполезно: в PATH мы ищем только git.exe. Сам bash
echo оттуда не берётся: после установки WSL2 первым там оказывается
echo C:\Windows\System32\bash.exe, а это запускалка подсистемы Linux, не оболочка.
set "TD_CALLER="
exit /b 1
