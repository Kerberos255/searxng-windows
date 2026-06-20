param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows"
)

$ErrorActionPreference = "Stop"

$Repo = Join-Path $Root "searxng"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Zip = Join-Path $Root "searxng-master.zip"
$DownloadZip = Join-Path $Root "searxng-master-new.zip"
$Extract = Join-Path $Root "_extract"
$Backup = Join-Path $Root ("searxng.backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if (!(Test-Path $Repo)) {
    Write-Host "SearXNG source not found: $Repo"
    exit 1
}

if (!(Test-Path $Python)) {
    Write-Host "Python venv not found: $Python"
    exit 1
}

$WasRunning = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8888/" -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) {
        $WasRunning = $true
        Write-Host "SearXNG is running, stopping before update..."
        & powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptRoot "stop.ps1") -Root $Root
        Start-Sleep -Seconds 2
    }
} catch {
}

Set-Location $Repo

if (Test-Path (Join-Path $Repo ".git")) {
    Write-Host "Current version:"
    git rev-parse --short HEAD
    git fetch origin
    git checkout master
    git pull --ff-only origin master
} else {
    Write-Host "Zip-based install detected, downloading latest source archive..."
    Invoke-WebRequest -Uri "https://github.com/searxng/searxng/archive/refs/heads/master.zip" -OutFile $DownloadZip
    Remove-Item -LiteralPath $Extract -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $Extract | Out-Null
    tar -xf $DownloadZip -C $Extract
    Move-Item -LiteralPath $Repo -Destination $Backup
    Move-Item -LiteralPath (Join-Path $Extract "searxng-master") -Destination $Repo
    Remove-Item -LiteralPath $Extract -Recurse -Force
    Move-Item -LiteralPath $DownloadZip -Destination $Zip -Force
    Write-Host "Previous source moved to: $Backup"
}

& powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptRoot "apply-windows-patch.ps1") -Root $Root

Set-Location $Repo
& $Python -m pip install -U pip setuptools wheel
& $Python -m pip install -r requirements.txt
& $Python -m pip install -e .
if ($LASTEXITCODE -ne 0) {
    Write-Host "Editable install failed with build isolation; retrying without build isolation."
    & $Python -m pip install --no-build-isolation -e .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Editable install failed."
        exit $LASTEXITCODE
    }
}

Write-Host "Update finished."

if ($WasRunning) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptRoot "start.ps1") -Root $Root
}
