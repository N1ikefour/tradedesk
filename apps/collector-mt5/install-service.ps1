#Requires -Version 5.1
<#
.SYNOPSIS
    Автозапуск коллектора MT5 через Планировщик заданий Windows (SPEC.md 8.2 п.4).

.DESCRIPTION
    Служба Windows из менеджера (S1-09) не выходит: это обычный процесс, и без обёртки
    вроде nssm служба его не переживёт. Планировщик заданий — то, что имеется в виду в
    спеке словами «регистрация при входе в систему».

    Задача запускает run-collector.bat --service, то есть тот же файл, которым коллектор
    запускается руками. Рабочая папка задаётся явно: по умолчанию Планировщик стартует
    задачу из C:\Windows\System32, и относительный LOG_DIR уехал бы туда.

    Вход в систему, а не «запускать независимо от входа»: терминал MetaTrader 5 —
    оконная программа, ей нужен рабочий стол пользователя. Заодно это избавляет от
    хранения пароля Windows в Планировщике.

.PARAMETER Remove
    Снять автозапуск: остановить коллектор и удалить задачу.

.PARAMETER Status
    Показать состояние задачи, процессы коллектора и хвост logs\run-collector.log.

.PARAMETER Stop
    Остановить коллектор, не трогая автозапуск (то же делает stop-collector.bat).

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

# Коды последнего запуска задачи. Планировщик показывает их шестнадцатеричными, а
# Get-ScheduledTaskInfo — десятичными; человеку не нужно ни то, ни другое.
# Ключи строками: коды не помещаются в Int32 целиком, а смешивать в одной таблице
# Int32 и Int64 нельзя — поиск по ней молча не находил бы половину значений.
$TaskResultText = @{
    '0'          = 'коллектор отработал и завершился — смотрите logs\run-collector.log'
    '1'          = 'коллектор завершился с ошибкой — смотрите logs\run-collector.log'
    '2'          = 'Планировщик не нашёл run-collector.bat — переустановите автозапуск'
    '267009'     = 'работает прямо сейчас'
    '267011'     = 'ещё ни разу не запускался'
    '267014'     = 'задачу остановили вручную'
    '2147942401' = 'Планировщик не нашёл файл задачи — переустановите автозапуск'
}

function Write-Step([string]$Text) { Write-Host $Text }
function Write-Note([string]$Text) { Write-Host "  $Text" -ForegroundColor DarkGray }
function Write-Warn([string]$Text) { Write-Host "ВНИМАНИЕ: $Text" -ForegroundColor Yellow }
function Write-Fail([string]$Text) { Write-Host "ОШИБКА: $Text" -ForegroundColor Red }

# ⚠️ В возвращаемой таблице лежит COLLECTOR_TOKEN. Печатать её целиком нельзя ни при
# какой ошибке (CLAUDE.md §5): вывод этого скрипта человек присылает разработчику.
function Read-CollectorEnv {
    $values = @{}
    if (-not (Test-Path -LiteralPath $EnvFile)) { return $values }
    foreach ($line in Get-Content -LiteralPath $EnvFile -Encoding UTF8) {
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
# файлу, а не по командной строке: процессы счетов порождаются через multiprocessing,
# и слова «collector» в их командной строке нет вовсе.
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

function Show-Terminals {
    $root = (Read-CollectorEnv)['MT5_PORTABLE_ROOT']
    if (-not $root) { return }
    $terminals = @(Get-CimInstance Win32_Process -Filter "Name = 'terminal64.exe'" |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($root, 'OrdinalIgnoreCase') })
    if ($terminals.Count -eq 0) { return }
    Write-Host ''
    Write-Warn "остались открытыми терминалы коллектора: $($terminals.Count) шт."
    foreach ($terminal in $terminals) {
        Write-Note "PID $($terminal.ProcessId) — $($terminal.ExecutablePath)"
    }
    Write-Note 'Коллектор не закрывает их сам (docs/mt5-assumptions.md, допущение 36).'
    Write-Note 'Каждый занимает 300-400 МБ. Закрыть можно окнами терминалов или'
    Write-Note 'в диспетчере задач; на данные это не влияет.'
}

function Stop-Collector {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Write-Step "Останавливаю задачу «$TaskName» ..."
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }

    $running = @(Get-CollectorProcess)
    if ($running.Count -eq 0) {
        Write-Step 'Процессов коллектора не осталось.'
        Show-Terminals
        return
    }

    # Менеджер гасится первым: живой менеджер поднимает процесс счёта заново в течение
    # своего тика, и порядок «сначала счета» оставил бы их поднятыми.
    $managers = @($running | Where-Object { $_.CommandLine -like '*collector.main*' })
    $workers = @($running | Where-Object { $_.CommandLine -notlike '*collector.main*' })
    foreach ($process in @($managers) + @($workers)) {
        Write-Step "Останавливаю процесс $($process.ProcessId) ..."
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2

    $left = @(Get-CollectorProcess)
    if ($left.Count -gt 0) {
        Write-Warn "не удалось остановить процессы: $($left.ProcessId -join ', '). Закройте их в диспетчере задач."
    } else {
        Write-Step 'Коллектор остановлен.'
    }
    Show-Terminals
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
    $managers = @($running | Where-Object { $_.CommandLine -like '*collector.main*' })
    Write-Step "Процессов коллектора: $($running.Count) (менеджеров: $($managers.Count), счетов: $($running.Count - $managers.Count))."
    if ($managers.Count -gt 1) {
        Write-Warn 'менеджеров больше одного — коллектор запущен дважды. Остановите всё (stop-collector.bat) и запустите заново.'
    }

    if (Test-Path -LiteralPath $RunLog) {
        Write-Step "Последние строки $RunLog :"
        Get-Content -LiteralPath $RunLog -Tail 15 | ForEach-Object { Write-Note $_ }
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

    # LOG_DIR и MT5_PORTABLE_ROOT в профиле пользователя — путь с кириллицей у первого
    # же пользователя (X-43) и папка, которую чистят «мастера очистки диска».
    $values = Read-CollectorEnv
    foreach ($key in @('MT5_PORTABLE_ROOT', 'LOG_DIR')) {
        $value = $values[$key]
        if (-not $value) { continue }
        if ($value.StartsWith($env:USERPROFILE, 'OrdinalIgnoreCase')) {
            Write-Warn "$key указывает внутрь профиля пользователя: $value"
            Write-Note 'Надёжнее короткий путь вида C:\td-terminals.'
        }
        if (-not (Test-AsciiPath $value)) {
            Write-Warn "$key содержит буквы вне латиницы: $value"
            Write-Note 'Терминал MetaTrader 5 — нативная программа, такие пути читает не всегда.'
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

    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force `
        -Description 'TradeDesk: синхронизация сделок из MetaTrader 5' | Out-Null

    Write-Step "Автозапуск установлен: задача «$TaskName» стартует через минуту после входа в систему."
    Write-Note "Пользователь: $me"
    Write-Note "Рабочая папка: $Here"
    Write-Note "Вывод запуска: $RunLog"
    Write-Host ''
    Write-Step 'Коллектор запускается после входа в систему, а не после включения'
    Write-Step 'компьютера: выключили на ночь — утром он поднимется, когда вы войдёте.'
    Write-Host ''
    Write-Step 'Остановить коллектор — файлом stop-collector.bat.'
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
    Start-ScheduledTask -TaskName $TaskName
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
