param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows",
    [string]$ProxyUrl = "",
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"

$RunScript = Join-Path $Root "scripts\run.ps1"
$BrokerRunScript = Join-Path $Root "scripts\run_broker.ps1"
$PidFile = Join-Path $Root "searxng.pid"
$BrokerPidFile = Join-Path $Root "broker.pid"
$Log = Join-Path $Root "searxng-run.log"
$ErrLog = Join-Path $Root "searxng-run.err.log"
$BrokerLog = Join-Path $Root "broker-run.log"
$BrokerErrLog = Join-Path $Root "broker-run.err.log"
$Url = "http://127.0.0.1:8888/"
$BrokerUrl = "http://127.0.0.1:8890/health"

if (!$EnvFile) {
    $EnvFile = Join-Path $Root "config\api-pool.env"
}

$BrokerRunning = $false
try {
    $r = Invoke-WebRequest -Uri $BrokerUrl -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) {
        Write-Host "API Pool Broker is already running: $BrokerUrl"
        $BrokerRunning = $true
    }
} catch {
}

if (!$BrokerRunning -and (Test-Path $BrokerPidFile)) {
    $OldPid = Get-Content -LiteralPath $BrokerPidFile -ErrorAction SilentlyContinue
    if ($OldPid -and (Get-Process -Id $OldPid -ErrorAction SilentlyContinue)) {
        Write-Host "API Pool Broker launcher already exists, PID: $OldPid"
        $BrokerRunning = $true
    } else {
        Remove-Item -LiteralPath $BrokerPidFile -Force -ErrorAction SilentlyContinue
    }
}

if (!$BrokerRunning) {
    Remove-Item -LiteralPath $BrokerLog -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $BrokerErrLog -Force -ErrorAction SilentlyContinue

    $BrokerArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", $BrokerRunScript,
        "-Root", $Root,
        "-EnvFile", $EnvFile
    )
    if ($ProxyUrl) {
        $BrokerArgs += @("-ProxyUrl", $ProxyUrl)
    }

    $BrokerProcess = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $BrokerArgs `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $BrokerLog `
        -RedirectStandardError $BrokerErrLog `
        -PassThru

    Set-Content -LiteralPath $BrokerPidFile -Value $BrokerProcess.Id -Encoding ASCII
    Start-Sleep -Seconds 4

    try {
        $r = Invoke-WebRequest -Uri $BrokerUrl -UseBasicParsing -TimeoutSec 5
        Write-Host "API Pool Broker started: $BrokerUrl"
    } catch {
        Write-Host "API Pool Broker did not respond. Check logs:"
        Write-Host $BrokerLog
        Write-Host $BrokerErrLog
        exit 1
    }
}

try {
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) {
        Write-Host "SearXNG is already running: $Url"
        exit 0
    }
} catch {
}

if (Test-Path $PidFile) {
    $OldPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
    if ($OldPid -and (Get-Process -Id $OldPid -ErrorAction SilentlyContinue)) {
        Write-Host "SearXNG launcher already exists, PID: $OldPid"
        exit 0
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

Remove-Item -LiteralPath $Log -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $ErrLog -Force -ErrorAction SilentlyContinue

$SearxngArgs = @("-ExecutionPolicy", "Bypass", "-File", $RunScript, "-Root", $Root)
if ($ProxyUrl) {
    $SearxngArgs += @("-ProxyUrl", $ProxyUrl)
}

$Process = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList $SearxngArgs `
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
