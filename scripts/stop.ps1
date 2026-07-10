param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows"
)

$ErrorActionPreference = "Continue"
$Stopped = $false

foreach ($Port in @(8888, 8890)) {
    $Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($Listener in $Listeners) {
        if ($Listener.OwningProcess -and $Listener.OwningProcess -ne $PID) {
            Stop-Process -Id $Listener.OwningProcess -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped listener on port $Port, PID: $($Listener.OwningProcess)"
            $Stopped = $true
        }
    }
}

foreach ($PidName in @("searxng.pid", "broker.pid")) {
    $PidFile = Join-Path $Root $PidName
    if (Test-Path $PidFile) {
        $LauncherPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
        if ($LauncherPid -and (Get-Process -Id $LauncherPid -ErrorAction SilentlyContinue)) {
            Stop-Process -Id $LauncherPid -Force -ErrorAction SilentlyContinue
            Write-Host "Stopped launcher PID: $LauncherPid"
            $Stopped = $true
        }
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    }
}

$EscapedRoot = [WildcardPattern]::Escape($Root)
$Processes = Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and $_.CommandLine -like "*$EscapedRoot*" -and (
        $_.CommandLine -like "*scripts*run.ps1*" -or
        $_.CommandLine -like "*scripts*run_broker.ps1*" -or
        $_.CommandLine -like "*searx*webapp.py*" -or
        $_.CommandLine -like "*api_pool*app.py*"
    )
}

foreach ($Process in $Processes) {
    Stop-Process -Id $Process.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "Stopped $($Process.Name) PID: $($Process.ProcessId)"
    $Stopped = $true
}

if ($Stopped) {
    Write-Host "SearXNG and API Pool Broker stopped."
} else {
    Write-Host "SearXNG and API Pool Broker were not running."
}
