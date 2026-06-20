param(
    [string]$Root = "E:\openclaw\searxng_windows"
)

$ErrorActionPreference = "Stop"

$RunScript = Join-Path $Root "scripts\run.ps1"
$PidFile = Join-Path $Root "searxng.pid"
$Log = Join-Path $Root "searxng-run.log"
$ErrLog = Join-Path $Root "searxng-run.err.log"
$Url = "http://127.0.0.1:8888/"

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
        Write-Host "SearXNG start process already exists, PID: $OldPid"
        exit 0
    }
}

Remove-Item -LiteralPath $Log -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $ErrLog -Force -ErrorAction SilentlyContinue

$Process = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList "-ExecutionPolicy", "Bypass", "-File", $RunScript, "-Root", $Root `
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
    Write-Host "SearXNG did not respond yet. Check logs:"
    Write-Host $Log
    Write-Host $ErrLog
    exit 1
}
