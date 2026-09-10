#Requires -Version 5.1
<#
.SYNOPSIS
    Автозапуск коллектора MT5 через Планировщик заданий Windows (SPEC.md 8.2 п.4).

.DESCRIPTION
    Служба Windows из коллектора не выходит: это обычный процесс, и без обёртки вроде
    nssm служба его не переживёт. Планировщик заданий — то, что имеется в виду в спеке
    словами «регистрация при входе в систему».

    Задача запускает run-collector.bat --service, то есть тот же файл, которым коллектор
    запускается руками. Рабочая папка задаётся явно: по умолчанию Планировщик стартует
    задачу из C:\Windows\System32, и относительный LOG_DIR уехал бы туда.

    Вход в систему, а не «запускать независимо от входа»: терминал MetaTrader 5 открывает
    сам человек (X-66), и это оконная программа — ей нужен рабочий стол сеанса. Заодно это
    избавляет от хранения пароля Windows в Планировщике.

.PARAMETER Remove
    Снять автозапуск: остановить коллектор и удалить задачу.

.PARAMETER Status
    Показать состояние задачи, процессы коллектора и хвост logs\run-collector.log.
    То же двойным кликом — status-collector.bat.

.PARAMETER Stop
    Остановить коллектор, не трогая автозапуск (то же делает stop-collector.bat).
    Сначала просьба выйти самому — файлом collector-stop.flag, который коллектор видит
    своим тиком, — и только потом сила. Сигнал чужому процессу на Windows не доставить,
    а TerminateProcess не доводит коллектор до прощального heartbeat.

    Терминал MetaTrader 5 остановка не закрывает и закрывать не должна: его открыл
    человек, и коллектор только отпускает свой канал к нему.

.PARAMETER NoStart
    При установке не запускать задачу сразу.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File install-service.ps1
#>
[CmdletBinding()]
param(
    [switch]$Remove,
    [switch]$Status,
    [switch]$Stop,
    [switch]$NoStart
)

$ErrorActionPreference = 'Stop'

$TaskName = 'TradeDesk Collector MT5'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Bat = Join-Path $Here 'run-collector.bat'
$VenvPython = Join-Path $Here '.venv\Scripts\python.exe'
$EnvFile = Join-Path $Here 'collector.env'
$RunLog = Join-Path $Here 'logs\run-collector.log'
# Тот же файл, что ищет коллектор (collector/main.py, STOP_FLAG_NAME): просьба выйти самому.
$StopFlag = Join-Path $Here 'collector-stop.flag'

# Сколько ждать, пока коллектор попрощается. Обычно это 1-2 секунды, но тик с недоступным
# API тянется минутами (ретраи httpx), и столько ждать по двойному клику нельзя: за
# потолком — принудительная остановка и честный текст про её цену.
$GracefulStopSeconds = 20

# Коды последнего запуска задачи. Планировщик показывает их шестнадцатеричными, а
# Get-ScheduledTaskInfo — десятичными; человеку не нужно ни то, ни другое.
# Ключи строками: коды не помещаются в Int32 целиком, а смешивать в одной таблице
# Int32 и Int64 нельзя — поиск по ней молча не находил бы половину значений.
#
# ⚠️ Коды 0-3 сюда приходят не от Планировщика, а от самого коллектора: это код выхода
# действия, то есть run-collector.bat. Их значения заданы в collector/main.py и
# продублированы в run-collector.bat; тексты обязаны совпадать с тамошними (закреплено
# тестом tests/test_install_files.py). Самый частый из них — 2: человек правит
# collector.env руками, и ошибка в нём видна только здесь и в хвосте лога.
$TaskResultText = @{
    '0'          = 'коллектор отработал и завершился — смотрите logs\run-collector.log'
    '1'          = 'коллектор аварийно остановился — смотрите logs\run-collector.log'
    '2'          = 'ошибка в collector.env — точную строку называет logs\run-collector.log'
    '3'          = 'коллектор работает только на Windows'
    '-1'         = 'коллектор сняли принудительно — stop-collector.bat или диспетчер задач'
    '4294967295' = 'коллектор сняли принудительно — stop-collector.bat или диспетчер задач'
    '267009'     = 'работает прямо сейчас'
    '267011'     = 'ещё ни разу не запускался'
    '267014'     = 'задачу остановили вручную'
    '2147942402' = 'Планировщик не нашёл run-collector.bat — переустановите автозапуск'
}

function Write-Step([string]$Text) { Write-Host $Text }
function Write-Note([string]$Text) { Write-Host "  $Text" -ForegroundColor DarkGray }
function Write-Warn([string]$Text) { Write-Host "ВНИМАНИЕ: $Text" -ForegroundColor Yellow }
function Write-Fail([string]$Text) { Write-Host "ОШИБКА: $Text" -ForegroundColor Red }

# Кодировка файлов, которые писал не PowerShell.
#
# `run-collector.log` пишет cmd.exe перенаправлением после `chcp 65001`, то есть UTF-8
# без BOM, а Windows PowerShell 5.1 без -Encoding читает такой файл как CP1251. Хвост
# лога — первое, куда смотрит человек, когда коллектор не поднялся, и кракозябры в нём
# стоят дороже всего (X-55). Но и `-Encoding UTF8` здесь было бы обещанием, которого мы
# дать не можем: под Планировщиком у задачи может не оказаться консоли вовсе, и какая
# кодовая страница у перенаправления тогда — вопрос, который на macOS не решить.
#
# Поэтому кодировка не назначается, а определяется. UTF-8 проверяется строго: русский
# текст в CP866 и CP1251 валидным UTF-8 не бывает (кириллица там — одиночные байты
# 0x80-0xFF, а UTF-8 требует за ведущим байтом продолжающий), поэтому строгая проверка
# отличает одно от другого без догадок. Не UTF-8 — читаем кодовой страницей OEM этой
# машины и говорим об этом: это находка, а не мелочь.
$script:LastEncodingNote = ''

function Read-FileBytes([string]$Path) {
    # Открывать надо с FileShare::ReadWrite: cmd.exe держит run-collector.log открытым на
    # дозапись, а ReadAllBytes дало бы на живом коллекторе нарушение совместного доступа —
    # то есть -Status отказывал бы ровно тогда, когда он и нужен.
    $stream = [System.IO.File]::Open(
        $Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite)
    try {
        $bytes = New-Object byte[] $stream.Length
        $total = 0
        while ($total -lt $bytes.Length) {
            $read = $stream.Read($bytes, $total, $bytes.Length - $total)
            if ($read -le 0) { break }
            $total += $read
        }
        return ,$bytes
    } finally {
        $stream.Dispose()
    }
}

function Read-TextFile([string]$Path) {
    $bytes = Read-FileBytes $Path
    try {
        $strict = New-Object System.Text.UTF8Encoding($false, $true)
        return $strict.GetString($bytes).TrimStart([char]0xFEFF)
    } catch {
        $page = 866
        try {
            $nls = 'HKLM:\SYSTEM\CurrentControlSet\Control\Nls\CodePage'
            $page = [int](Get-ItemProperty -Path $nls -Name 'OEMCP').OEMCP
        } catch {
            # Реестр не прочитался — берём CP866, кодовую страницу русской консоли.
        }
        $script:LastEncodingNote = "файл не в UTF-8, прочитан кодовой страницей $page — если текст ниже нечитаем, дело в этом"
        return [System.Text.Encoding]::GetEncoding($page).GetString($bytes)
    }
}

function Read-TextLines([string]$Path) {
    return @((Read-TextFile $Path) -split "\r?\n")
}

# ⚠️ В возвращаемой таблице лежит COLLECTOR_TOKEN. Печатать её целиком нельзя ни при
# какой ошибке (CLAUDE.md §5): вывод этого скрипта человек присылает разработчику.
function Read-CollectorEnv {
    $values = @{}
    if (-not (Test-Path -LiteralPath $EnvFile)) { return $values }
    foreach ($line in Read-TextLines $EnvFile) {
        $text = $line.Trim()
        if (-not $text -or $text.StartsWith('#')) { continue }
        $split = $text.IndexOf('=')
        if ($split -lt 1) { continue }
        $key = $text.Substring(0, $split).Trim().ToUpperInvariant()
        $value = $text.Substring($split + 1).Trim().Trim('"').Trim("'")
        $values[$key] = $value
    }
    return $values
}

# Процессы коллектора — это python.exe из нашего .venv, и только он. Отбор по пути к
# файлу, а не по командной строке: процесс у коллектора теперь один (X-66), но искать его
# надёжнее по пути — командную строку Windows отдаёт не всегда.
function Get-CollectorProcess {
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.ExecutablePath -and ($_.ExecutablePath -eq $VenvPython) }
}

function Test-AsciiPath([string]$Path) {
    foreach ($char in $Path.ToCharArray()) {
        if ([int]$char -gt 126 -or [int]$char -lt 32) { return $false }
    }
    return $true
}

# Просьба остановиться, а не выстрел. Сигнал чужому процессу на Windows не доставить, а
# Stop-Process и «Снять задачу» — это TerminateProcess: коллектор не доходит до своего
# _shutdown, то есть не отпускает канал к терминалу и не шлёт прощальный heartbeat.
# Сирот после этого не остаётся — процесс у коллектора один (X-66 снял X-57), — но на
# карточках счетов разницы между исходами по-прежнему нет никакой.
function Request-GracefulStop {
    try {
        New-Item -ItemType File -Path $StopFlag -Force | Out-Null
    } catch {
        Write-Note "не удалось создать $StopFlag — остановлю принудительно."
        return $false
    }
    Write-Step "Прошу менеджер остановиться сам (до $GracefulStopSeconds с) ..."
    for ($second = 0; $second -lt $GracefulStopSeconds; $second++) {
        Start-Sleep -Seconds 1
        if (@(Get-CollectorProcess).Count -eq 0) { return $true }
    }
    return $false
}

function Remove-StopFlag {
    if (-not (Test-Path -LiteralPath $StopFlag)) { return }
    try {
        Remove-Item -LiteralPath $StopFlag -Force
    } catch {
        Write-Note "остался файл $StopFlag — удалите его вручную, иначе он ничему не мешает."
    }
}

function Stop-Collector {
    $found = @(Get-CollectorProcess).Count
    $graceful = $false
    if ($found -gt 0) { $graceful = Request-GracefulStop }

    # Задача Планировщика гасится ПОСЛЕ просьбы, а не до неё: Stop-ScheduledTask снимает
    # дерево процессов задачи целиком, то есть убил бы менеджер раньше, чем тот успел бы
    # попрощаться, — а ради прощания всё и затевалось.
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Write-Step "Останавливаю задачу «$TaskName» ..."
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }

    $running = @(Get-CollectorProcess)
    foreach ($process in $running) {
        Write-Step "Останавливаю процесс $($process.ProcessId) ..."
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($running.Count -gt 0) { Start-Sleep -Seconds 2 }

    Remove-StopFlag
    $left = @(Get-CollectorProcess)
    if ($left.Count -gt 0) {
        Write-Warn "не удалось остановить процессы: $($left.ProcessId -join ', '). Закройте их в диспетчере задач."
    } elseif ($found -eq 0) {
        Write-Step 'Процессов коллектора и не было.'
    } elseif ($graceful) {
        Write-Step 'Коллектор остановлен: он успел попрощаться.'
        Write-Note 'Процессов коллектора не осталось, а окно MetaTrader 5 он не закрывает —'
        Write-Note 'терминал открывали вы, и он остаётся как есть.'
        Write-Note 'На карточках счетов сразу не изменится ничего, а минут через пять'
        Write-Note 'там появится «коллектор не на связи». Это правда, а не поломка:'
        Write-Note 'вы его и остановили. Данные не теряются — следующий запуск'
        Write-Note 'заберёт своё окно целиком.'
    } else {
        Write-Step 'Коллектор остановлен принудительно: сам он выйти не успел.'
        Write-Note 'О такой остановке TradeDesk не узнаёт: на карточках счетов останется'
        Write-Note 'последнее состояние, а минут через пять — «коллектор не на связи».'
        Write-Note 'После остановки это ожидаемо. Данные не теряются: следующий запуск'
        Write-Note 'заберёт своё окно целиком.'
    }
}

function Show-Status {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Step "Автозапуск не установлен: задачи «$TaskName» в Планировщике нет."
    } else {
        $info = Get-ScheduledTaskInfo -TaskName $TaskName
        $code = [int64]$info.LastTaskResult
        $text = $TaskResultText["$code"]
        if (-not $text) { $text = "код $code" }
        Write-Step "Задача «$TaskName»: состояние $($task.State)."
        Write-Note "Последний запуск: $($info.LastRunTime) — $text"
    }

    $running = @(Get-CollectorProcess)
    Write-Step "Процессов коллектора: $($running.Count) (должен быть один)."
    if ($running.Count -gt 1) {
        Write-Warn 'процессов больше одного — коллектор запущен дважды, и оба борются за один канал к терминалу. Остановите всё (stop-collector.bat) и запустите заново.'
    }
    $terminals = @(Get-CimInstance Win32_Process -Filter "Name = 'terminal64.exe'")
    if ($terminals.Count -eq 0) {
        Write-Warn 'MetaTrader 5 не запущен. Коллектор синхронизирует тот счёт, который открыт в терминале: откройте терминал и войдите в счёт.'
    } else {
        Write-Step "Терминалов MetaTrader 5 открыто: $($terminals.Count)."
    }

    if (Test-Path -LiteralPath $RunLog) {
        Write-Step "Последние строки $RunLog :"
        $script:LastEncodingNote = ''
        try {
            $lines = @(Read-TextLines $RunLog | Where-Object { $_.Trim() -ne '' })
            foreach ($line in @($lines | Select-Object -Last 15)) { Write-Note $line }
            if ($script:LastEncodingNote) { Write-Warn $script:LastEncodingNote }
        } catch {
            Write-Warn "не удалось прочитать $RunLog : $($_.Exception.Message)"
        }
    } else {
        Write-Step "Файла $RunLog ещё нет — задача ни разу не отработала."
    }

    Write-Host ''
    Write-Step 'Что со счетами на самом деле — видно в TradeDesk на экране «Счета»:'
    Write-Step 'коллектор сообщает о себе туда, а не в Планировщик.'
}

function Install-Task {
    if (-not (Test-Path -LiteralPath $Bat)) {
        Write-Fail "рядом со скриптом нет run-collector.bat. Распакуйте архив релиза целиком."
        exit 1
    }
    if (-not (Test-AsciiPath $Here)) {
        Write-Fail "в пути установки есть буквы вне латиницы: $Here"
        Write-Note 'Перенесите папку установки в корень диска (например, C:\tradedesk) и повторите.'
        exit 1
    }
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Write-Fail 'коллектор ещё ни разу не запускался вручную.'
        Write-Note 'Сначала запустите run-collector.bat и убедитесь, что счета появились'
        Write-Note 'в TradeDesk. Автозапуск ставится на то, что уже работает.'
        exit 1
    }
    if (-not (Test-Path -LiteralPath $EnvFile)) {
        Write-Fail "нет файла настроек $EnvFile. Запустите run-collector.bat — он его создаст."
        exit 1
    }

    # LOG_DIR и STATE_DIR в профиле пользователя — путь с кириллицей у первого же
    # пользователя (X-43) и папка, которую чистят «мастера очистки диска».
    $values = Read-CollectorEnv
    foreach ($key in @('STATE_DIR', 'LOG_DIR')) {
        $value = $values[$key]
        if (-not $value) { continue }
        if ($value.StartsWith($env:USERPROFILE, 'OrdinalIgnoreCase')) {
            Write-Warn "$key указывает внутрь профиля пользователя: $value"
            Write-Note 'Надёжнее оставить относительный путь: он считается от папки установки.'
        }
        if (-not (Test-AsciiPath $value)) {
            Write-Warn "$key содержит буквы вне латиницы: $value"
            Write-Note 'Python и терминал MetaTrader 5 — нативные программы, такие пути читают не всегда.'
        }
    }

    $me = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\cmd.exe" `
        -Argument "/c ""$Bat"" --service" -WorkingDirectory $Here
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $me
    # Минута форы: за вход в систему разом берутся Docker Desktop, антивирус и всё
    # остальное, а коллектору без поднятого TradeDesk всё равно нечего спрашивать.
    $trigger.Delay = 'PT1M'
    $principal = New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -MultipleInstances IgnoreNew `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero)

    try {
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
            -Principal $principal -Settings $settings -Force `
            -Description 'TradeDesk: синхронизация сделок из MetaTrader 5' | Out-Null
    } catch {
        # Планировщик отказывает по-английски и подробностями операционной системы.
        # Человеку нужен не текст ошибки, а что с ним делать, поэтому сначала — что делать.
        Write-Fail 'Планировщик заданий отказался завести задачу.'
        Write-Note 'Чаще всего это одно из трёх:'
        Write-Note '  политика организации запрещает создавать задачи;'
        Write-Note '  служба «Планировщик заданий» отключена (services.msc);'
        Write-Note '  скрипт запущен под учётной записью без своих задач.'
        Write-Note 'Коллектор при этом работает: запускайте run-collector.bat руками,'
        Write-Note 'а автозапуск можно завести через taskschd.msc — что именно там'
        Write-Note 'создавать, написано в docs\collector-windows-checklist.md, шаг D-1.'
        Write-Note ''
        Write-Note "Ответ Планировщика: $($_.Exception.Message)"
        exit 1
    }

    Write-Step "Автозапуск установлен: задача «$TaskName» стартует через минуту после входа в систему."
    Write-Note "Пользователь: $me"
    Write-Note "Рабочая папка: $Here"
    Write-Note "Вывод запуска: $RunLog"
    Write-Host ''
    Write-Step 'Коллектор запускается после входа в систему, а не после включения'
    Write-Step 'компьютера: выключили на ночь — утром он поднимется, когда вы войдёте.'
    Write-Host ''
    Write-Step 'Остановить коллектор — файлом stop-collector.bat: он сначала просит'
    Write-Step 'коллектор выйти самому и только потом снимает силой.'
    Write-Step 'Посмотреть, что с ним сейчас, — файлом status-collector.bat.'
    Write-Warn '«Снять задачу» в диспетчере задач останавливает не всё: процессы счетов'
    Write-Note 'переживают такую остановку и продолжают синхронизацию (X-57). После неё'
    Write-Note 'проверьте диспетчер или запустите stop-collector.bat.'

    if ($NoStart) { return }

    $running = @(Get-CollectorProcess)
    if ($running.Count -gt 0) {
        Write-Host ''
        Write-Warn 'коллектор уже запущен — задачу сейчас не стартую, чтобы не поднять второй.'
        return
    }
    Write-Host ''
    Write-Step 'Запускаю задачу ...'
    try {
        Start-ScheduledTask -TaskName $TaskName
    } catch {
        Write-Warn 'задача заведена, но запустить её сейчас не вышло.'
        Write-Note "Ответ Планировщика: $($_.Exception.Message)"
        Write-Note 'Запустите run-collector.bat руками; после входа в систему задача'
        Write-Note 'попробует стартовать сама.'
        return
    }
    Start-Sleep -Seconds 10
    Write-Host ''
    Show-Status
}

function Remove-Task {
    Stop-Collector
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Step 'Автозапуска и не было: задачи в Планировщике нет.'
        return
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Step "Автозапуск снят: задача «$TaskName» удалена."
    Write-Note 'Настройки и логи остались на месте; запуск вручную по-прежнему работает.'
}

if ($env:OS -ne 'Windows_NT') {
    Write-Fail 'коллектор MT5 работает только на Windows.'
    exit 3
}

if ($Status) { Show-Status; exit 0 }
if ($Stop) { Stop-Collector; exit 0 }
if ($Remove) { Remove-Task; exit 0 }
Install-Task
exit 0
