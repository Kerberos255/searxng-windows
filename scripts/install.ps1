param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows",
    [string]$RuntimePython = "python"
)

$ErrorActionPreference = "Stop"

$Repo = Join-Path $Root "searxng"
$Zip = Join-Path $Root "searxng-master.zip"
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
$SourceExtractor = Join-Path $RepoRoot "scripts\extract-source.py"
$LauncherNames = @(
    "start-searxng.cmd",
    "stop-searxng.cmd",
    "check-searxng.cmd"
)

$PythonCommand = Get-Command $RuntimePython -ErrorAction SilentlyContinue

if (!$PythonCommand) {
    Write-Host "Runtime Python not found in PATH or as a file: $RuntimePython"
    exit 1
}

$RuntimePythonResolved = $PythonCommand.Source

New-Item -ItemType Directory -Force -Path $Root | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "scripts"), (Join-Path $Root "config"), (Join-Path $Root "api_pool"), (Join-Path $Root "patches") | Out-Null

if ((Resolve-Path -LiteralPath $ScriptRoot).Path -ne (Resolve-Path -LiteralPath (Join-Path $Root "scripts")).Path) {
    Copy-Item -Path (Join-Path $ScriptRoot "*") -Destination (Join-Path $Root "scripts") -Recurse -Force
}

if ((Resolve-Path -LiteralPath $RepoRoot).Path -ne (Resolve-Path -LiteralPath $Root).Path) {
    Copy-Item -Path (Join-Path $RepoRoot "api_pool\*") -Destination (Join-Path $Root "api_pool") -Recurse -Force
    Copy-Item -Path (Join-Path $RepoRoot "patches\*") -Destination (Join-Path $Root "patches") -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $RepoRoot "config\settings.example.yml") -Destination (Join-Path $Root "config\settings.example.yml") -Force
    Copy-Item -LiteralPath (Join-Path $RepoRoot "config\api-pool.env.example") -Destination (Join-Path $Root "config\api-pool.env.example") -Force
    foreach ($LauncherName in $LauncherNames) {
        Copy-Item -LiteralPath (Join-Path $RepoRoot $LauncherName) -Destination (Join-Path $Root $LauncherName) -Force
    }
}

$ApiPoolEnv = Join-Path $Root "config\api-pool.env"
$ApiPoolEnvExample = Join-Path $Root "config\api-pool.env.example"
if (!(Test-Path -LiteralPath $ApiPoolEnv) -and (Test-Path -LiteralPath $ApiPoolEnvExample)) {
    Copy-Item -LiteralPath $ApiPoolEnvExample -Destination $ApiPoolEnv
    Write-Host "Created config\api-pool.env with empty API key placeholders."
}

$SettingsPath = Join-Path $Root "config\settings.yml"
$SettingsExample = Join-Path $RepoRoot "config\settings.example.yml"
if (!(Test-Path -LiteralPath $SettingsPath) -and (Test-Path -LiteralPath $SettingsExample)) {
    Copy-Item -LiteralPath $SettingsExample -Destination $SettingsPath
    $Secret = (& $RuntimePythonResolved -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
    if ($LASTEXITCODE -ne 0 -or !$Secret) {
        throw "Failed to generate the local SearXNG secret_key."
    }
    $SettingsText = Get-Content -LiteralPath $SettingsPath -Raw
    $SettingsText = $SettingsText.Replace("CHANGE_ME_GENERATE_WITH_SECRETS_TOKEN_URLSAFE", $Secret)
    Set-Content -LiteralPath $SettingsPath -Value $SettingsText -Encoding UTF8
    Write-Host "Created config\settings.yml from example and generated a local secret_key."
}

$RepoIsValid = [System.IO.File]::Exists((Join-Path $Repo "setup.py")) -and
    [System.IO.File]::Exists((Join-Path $Repo "requirements.txt")) -and
    [System.IO.File]::Exists((Join-Path $Repo "searx\webapp.py"))

if (!$RepoIsValid) {
    if (![System.IO.File]::Exists($SourceExtractor)) {
        throw "SearXNG ZIP extractor not found: $SourceExtractor"
    }

    $Staging = Join-Path $Root ("_searxng-install-" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Force -Path $Staging | Out-Null
        Write-Host "Downloading the upstream SearXNG source archive..."
        Invoke-WebRequest -Uri "https://github.com/searxng/searxng/archive/refs/heads/master.zip" -OutFile $Zip -UseBasicParsing

        & $RuntimePythonResolved $SourceExtractor $Zip $Staging
        if ($LASTEXITCODE -ne 0) {
            throw "SearXNG source extraction failed with exit code $LASTEXITCODE."
        }
        if (![System.IO.File]::Exists((Join-Path $Staging "setup.py")) -or
            ![System.IO.File]::Exists((Join-Path $Staging "requirements.txt")) -or
            ![System.IO.File]::Exists((Join-Path $Staging "searx\webapp.py"))) {
            throw "The extracted SearXNG source is incomplete."
        }

        if ([System.IO.Directory]::Exists($Repo)) {
            $IncompleteBackup = Join-Path $Root ("searxng.incomplete-" + (Get-Date -Format "yyyyMMdd-HHmmss") + "-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
            Move-Item -LiteralPath $Repo -Destination $IncompleteBackup
            Write-Host "Preserved the incomplete source directory at: $IncompleteBackup"
        }

        Move-Item -LiteralPath $Staging -Destination $Repo
        Write-Host "Upstream SearXNG source is ready."
    } finally {
        if ([System.IO.Directory]::Exists($Staging)) {
            Remove-Item -LiteralPath $Staging -Recurse -Force
        }
    }
}

if (!(Test-Path -LiteralPath $Python -PathType Leaf)) {
    & $RuntimePythonResolved -m venv $Venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the Python virtual environment."
    }
}

& $Python -m pip install -U pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip, setuptools, and wheel."
}

Push-Location $Repo
try {
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

& powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptRoot "apply-windows-patch.ps1") -Root $Root
if ($LASTEXITCODE -ne 0) {
    throw "Failed to apply the Windows compatibility patch."
}

Write-Host ""
Write-Host "Install finished."
Write-Host "Create config\settings.yml from config\settings.example.yml if needed."
Write-Host "Then double-click: $Root\start-searxng.cmd"
Write-Host "PowerShell alternative: powershell -ExecutionPolicy Bypass -File $Root\scripts\start.ps1"
