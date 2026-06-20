param(
    [string]$Root = "E:\openclaw\searxng_windows"
)

$ErrorActionPreference = "Continue"

$PidFile = Join-Path $Root "searxng.pid"
$Stopped = $false

if (Test-Path $PidFile) {
    $LauncherPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
    if ($LauncherPid) {
        $p = Get-Process -Id $LauncherPid -ErrorAction SilentlyContinue
        if ($p) {
            Stop-Process -Id $LauncherPid -Force
            Write-Host "Stopped launcher PID: $LauncherPid"
            $Stopped = $true
        }
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

$EscapedRoot = [WildcardPattern]::Escape($Root)
$Processes = Get-CimInstance Win32_Process | Where-Object {
    ($_.CommandLine -like "*$EscapedRoot*scripts*run.ps1*") -or
    ($_.CommandLine -like "*$EscapedRoot*.venv*Scripts*python.exe*searx*webapp.py*") -or
    ($_.CommandLine -like "*searx\webapp.py*" -and $_.CommandLine -like "*$EscapedRoot*")
}

foreach ($Process in $Processes) {
    if ($Process.ProcessId -ne $PID) {
        Stop-Process -Id $Process.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped $($Process.Name) PID: $($Process.ProcessId)"
        $Stopped = $true
    }
}

if (!$Stopped) {
    Write-Host "SearXNG was not running."
} else {
    Write-Host "SearXNG stopped."
}
