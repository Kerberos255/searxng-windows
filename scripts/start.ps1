param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows",
    [string]$ProxyUrl = "",
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"

try {
    $Root = [System.IO.Path]::GetFullPath($Root)
} catch {
    Write-Host "Invalid installation root path: $Root"
    Write-Host $_
    exit 1
}

function Quote-NativeArgument {
    param([AllowEmptyString()][string]$Value)

    $Quoted = New-Object System.Text.StringBuilder
    [void]$Quoted.Append('"')
    $Backslashes = 0
    foreach ($Character in $Value.ToCharArray()) {
        if ($Character -eq [char]92) {
            $Backslashes++
            continue
        }
        if ($Character -eq [char]34) {
            [void]$Quoted.Append(('\' * ($Backslashes * 2 + 1)))
            [void]$Quoted.Append('"')
            $Backslashes = 0
            continue
        }
        if ($Backslashes -gt 0) {
            [void]$Quoted.Append(('\' * $Backslashes))
            $Backslashes = 0
        }
        [void]$Quoted.Append($Character)
    }
    if ($Backslashes -gt 0) {
        [void]$Quoted.Append(('\' * ($Backslashes * 2)))
    }
    [void]$Quoted.Append('"')
    return $Quoted.ToString()
}

function Join-NativeArguments {
    param([string[]]$Values)
    return (($Values | ForEach-Object { Quote-NativeArgument $_ }) -join ' ')
}

$RunScript = Join-Path $Root "scripts\run.ps1"
$BrokerRunScript = Join-Path $Root "scripts\run_broker.ps1"
$ApiPoolHelper = Join-Path $Root "scripts\api-pool.ps1"
$PidFile = Join-Path $Root "searxng.pid"
$BrokerPidFile = Join-Path $Root "broker.pid"
$Log = Join-Path $Root "searxng-run.log"
$ErrLog = Join-Path $Root "searxng-run.err.log"
$BrokerLog = Join-Path $Root "broker-run.log"
$BrokerErrLog = Join-Path $Root "broker-run.err.log"
$BrokerConsoleErrLog = Join-Path $Root "broker-console.err.log"
$Url = "http://127.0.0.1:8888/"
$BrokerUrl = "http://127.0.0.1:8890/health"

function Protect-LogFile {
    param([string]$Path)
    if (![System.IO.File]::Exists($Path)) { return }
    try {
        $Content = [System.IO.File]::ReadAllText($Path)
        $Redacted = [System.Text.RegularExpressions.Regex]::Replace(
            $Content,
            '(?i)(?<path>(?:https?://|/)[^\s?"]+)\?[^\s"]*',
            '$1?[REDACTED]'
        )
        if ($Redacted -ne $Content) {
            [System.IO.File]::WriteAllText(
                $Path,
                $Redacted,
                [System.Text.UTF8Encoding]::new($false)
            )
        }
    } catch {
        Write-Warning "Could not redact an existing log file: $Path"
        throw
    }
}

function Rotate-LogFile {
    param(
        [string]$Path,
        [int]$BackupCount = 3
    )
    for ($Index = $BackupCount; $Index -ge 1; $Index--) {
        $Source = if ($Index -eq 1) { $Path } else { "$Path.$($Index - 1)" }
        $Destination = "$Path.$Index"
        if ([System.IO.File]::Exists($Destination)) {
            Remove-Item -LiteralPath $Destination -Force
        }
        if ([System.IO.File]::Exists($Source)) {
            Move-Item -LiteralPath $Source -Destination $Destination -Force
        }
    }
}

if (![System.IO.File]::Exists($ApiPoolHelper)) {
    Write-Host "API Pool helper not found: $ApiPoolHelper"
    exit 1
}
. $ApiPoolHelper
$ApiPoolEnabled = Test-ApiPoolEnabled -Root $Root

if (!$EnvFile) {
    $EnvFile = Join-Path $Root "config\api-pool.env"
}

if ($ApiPoolEnabled) {
    $BrokerRunning = $false
    try {
        $r = Invoke-WebRequest -Uri $BrokerUrl -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) {
            Write-Host "API Pool Broker is already running: $BrokerUrl"
            $BrokerRunning = $true
        }
    } catch {
    }

    if (!$BrokerRunning -and [System.IO.File]::Exists($BrokerPidFile)) {
        $OldPid = Get-Content -LiteralPath $BrokerPidFile -ErrorAction SilentlyContinue
        if ($OldPid -and (Get-Process -Id $OldPid -ErrorAction SilentlyContinue)) {
            Write-Host "API Pool Broker launcher already exists, PID: $OldPid"
            $BrokerRunning = $true
        } else {
            Remove-Item -LiteralPath $BrokerPidFile -Force -ErrorAction SilentlyContinue
        }
    }

    if (!$BrokerRunning) {
        foreach ($Path in @($BrokerErrLog, "$BrokerErrLog.1", "$BrokerErrLog.2", "$BrokerErrLog.3")) {
            Protect-LogFile -Path $Path
        }
        foreach ($Path in @($BrokerLog, $BrokerConsoleErrLog)) {
            Protect-LogFile -Path $Path
            Rotate-LogFile -Path $Path
        }

        $BrokerArgs = @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", $BrokerRunScript,
            "-Root", $Root,
            "-EnvFile", $EnvFile
        )
        if ($ProxyUrl) {
            $BrokerArgs += @("-ProxyUrl", $ProxyUrl)
        }

        $BrokerProcess = Start-Process `
            -FilePath "powershell.exe" `
            -ArgumentList (Join-NativeArguments $BrokerArgs) `
            -WorkingDirectory $Root `
            -WindowStyle Hidden `
            -RedirectStandardOutput $BrokerLog `
            -RedirectStandardError $BrokerConsoleErrLog `
            -PassThru

        Set-Content -LiteralPath $BrokerPidFile -Value $BrokerProcess.Id -Encoding ASCII
        $BrokerReady = $false
        $Deadline = [DateTime]::UtcNow.AddSeconds(30)
        while ([DateTime]::UtcNow -lt $Deadline) {
            if ($BrokerProcess.HasExited) {
                Write-Host "API Pool Broker launcher exited during startup: $($BrokerProcess.ExitCode)"
                break
            }
            try {
                $r = Invoke-WebRequest -Uri $BrokerUrl -UseBasicParsing -TimeoutSec 1
                if ($r.StatusCode -eq 200) {
                    $BrokerReady = $true
                    break
                }
            } catch {
            }
            Start-Sleep -Milliseconds 500
        }

        if ($BrokerReady) {
            Write-Host "API Pool Broker started: $BrokerUrl"
        } else {
            Write-Host "API Pool Broker did not become healthy within 30 seconds. Check logs:"
            Write-Host $BrokerLog
            Write-Host $BrokerErrLog
            Write-Host $BrokerConsoleErrLog
            exit 1
        }
    }
} else {
    Write-Host "API Pool is disabled in config\settings.yml; Broker startup skipped."
}

try {
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) {
        Write-Host "SearXNG is already running: $Url"
        exit 0
    }
} catch {
}

if ([System.IO.File]::Exists($PidFile)) {
    $OldPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
    if ($OldPid -and (Get-Process -Id $OldPid -ErrorAction SilentlyContinue)) {
        Write-Host "SearXNG launcher already exists, PID: $OldPid"
        exit 0
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

foreach ($Path in @($Log, $ErrLog)) {
    Protect-LogFile -Path $Path
    foreach ($Index in @(1, 2, 3)) { Protect-LogFile -Path "$Path.$Index" }
    Rotate-LogFile -Path $Path
}

$SearxngArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $RunScript, "-Root", $Root)
if ($ProxyUrl) {
    $SearxngArgs += @("-ProxyUrl", $ProxyUrl)
}

$Process = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList (Join-NativeArguments $SearxngArgs) `
    -WorkingDirectory $Root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $Log `
    -RedirectStandardError $ErrLog `
    -PassThru

Set-Content -LiteralPath $PidFile -Value $Process.Id -Encoding ASCII
Start-Sleep -Seconds 6

try {
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
    Write-Host "SearXNG started: $Url"
    Write-Host "Launcher PID: $($Process.Id)"
    exit 0
} catch {
    Write-Host "SearXNG did not respond. Check logs:"
    Write-Host $Log
    Write-Host $ErrLog
    exit 1
}
