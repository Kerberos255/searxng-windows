param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows"
)

$ErrorActionPreference = "Stop"

$Repo = Join-Path $Root "searxng"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Zip = Join-Path $Root "searxng-master.zip"
$DownloadZip = Join-Path $Root "searxng-master-new.zip"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceExtractor = Join-Path $ScriptRoot "extract-source.py"
$Backup = Join-Path $Root ("searxng.backup-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8))

if (!(Test-Path -LiteralPath $Python -PathType Leaf)) {
    Write-Host "Python venv not found: $Python"
    exit 1
}

if (![System.IO.File]::Exists($SourceExtractor)) {
    Write-Host "SearXNG ZIP extractor not found: $SourceExtractor"
    exit 1
}

$WasRunning = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8888/" -UseBasicParsing -TimeoutSec 3
    if ($r.StatusCode -eq 200) {
        $WasRunning = $true
    }
} catch {
}

if ($WasRunning) {
    Write-Host "SearXNG is running, stopping before update..."
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptRoot "stop.ps1") -Root $Root
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to stop SearXNG before updating."
    }
    Start-Sleep -Seconds 2
}

$Staging = Join-Path $Root ("_searxng-update-" + [guid]::NewGuid().ToString("N"))
$UpdateSucceeded = $false
$SourceMovedToBackup = $false

try {
    New-Item -ItemType Directory -Force -Path $Staging | Out-Null
    Write-Host "Downloading the upstream SearXNG source archive..."
    Invoke-WebRequest -Uri "https://github.com/searxng/searxng/archive/refs/heads/master.zip" -OutFile $DownloadZip -UseBasicParsing

    & $Python $SourceExtractor $DownloadZip $Staging
    if ($LASTEXITCODE -ne 0) {
        throw "SearXNG source extraction failed with exit code $LASTEXITCODE."
    }

    if (![System.IO.File]::Exists((Join-Path $Staging "setup.py")) -or
        ![System.IO.File]::Exists((Join-Path $Staging "requirements.txt")) -or
        ![System.IO.File]::Exists((Join-Path $Staging "searx\webapp.py"))) {
        throw "The extracted SearXNG source is incomplete."
    }

    if ([System.IO.Directory]::Exists($Repo)) {
        Move-Item -LiteralPath $Repo -Destination $Backup
        $SourceMovedToBackup = $true
    }

    try {
        Move-Item -LiteralPath $Staging -Destination $Repo

        & powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptRoot "apply-windows-patch.ps1") -Root $Root
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to apply the Windows compatibility patch."
        }

        Push-Location $Repo
        try {
            & $Python -m pip install -U pip setuptools wheel
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to upgrade pip, setuptools, and wheel."
            }

            & $Python -m pip install -r requirements.txt
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to install SearXNG requirements."
            }

            $ApiPoolRequirements = Join-Path $Root "api_pool\requirements.txt"
            if (Test-Path -LiteralPath $ApiPoolRequirements -PathType Leaf) {
                & $Python -m pip install -r $ApiPoolRequirements
                if ($LASTEXITCODE -ne 0) {
                    throw "Failed to install API Pool requirements."
                }
            }

            # Upstream packaging imports runtime dependencies already installed above.
            & $Python -m pip install --no-build-isolation -e .
            if ($LASTEXITCODE -ne 0) {
                throw "Editable install failed with exit code $LASTEXITCODE."
            }
        } finally {
            Pop-Location
        }

        Move-Item -LiteralPath $DownloadZip -Destination $Zip -Force
        $UpdateSucceeded = $true
        if ($SourceMovedToBackup) {
            Write-Host "Previous source backup: $Backup"
        }
        Write-Host "Update finished."
    } catch {
        if ([System.IO.Directory]::Exists($Repo)) {
            Remove-Item -LiteralPath $Repo -Recurse -Force
        }
        if ($SourceMovedToBackup -and [System.IO.Directory]::Exists($Backup)) {
            Move-Item -LiteralPath $Backup -Destination $Repo
            Write-Host "Restored the previous SearXNG source after the update failed."
        }
        throw
    }
} catch {
    if ($WasRunning -and [System.IO.Directory]::Exists($Repo)) {
        Write-Host "Update failed; attempting to restart the previous SearXNG service..."
        & powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptRoot "start.ps1") -Root $Root
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Automatic restart failed. Check the SearXNG logs."
        }
    }
    throw
} finally {
    if ([System.IO.Directory]::Exists($Staging)) {
        Remove-Item -LiteralPath $Staging -Recurse -Force
    }
    if (!$UpdateSucceeded -and [System.IO.File]::Exists($DownloadZip)) {
        Remove-Item -LiteralPath $DownloadZip -Force
    }
}

if ($WasRunning) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptRoot "start.ps1") -Root $Root
    if ($LASTEXITCODE -ne 0) {
        throw "Update succeeded, but SearXNG did not restart successfully."
    }
}
