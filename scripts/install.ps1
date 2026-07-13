param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows",
    [string]$RuntimePython = "python"
)

$ErrorActionPreference = "Stop"

$Repo = Join-Path $Root "searxng"
$Zip = Join-Path $Root "searxng-master.zip"
$Extract = Join-Path $Root "_extract"
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
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
New-Item -ItemType Directory -Force -Path `
    (Join-Path $Root "scripts"), `
    (Join-Path $Root "config"), `
    (Join-Path $Root "api_pool"), `
    (Join-Path $Root "patches") | Out-Null

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
if (!(Test-Path $ApiPoolEnv) -and (Test-Path $ApiPoolEnvExample)) {
    Copy-Item -LiteralPath $ApiPoolEnvExample -Destination $ApiPoolEnv
    Write-Host "Created config\api-pool.env with empty API key placeholders."
}

if (!(Test-Path (Join-Path $Root "config\settings.yml")) -and (Test-Path (Join-Path $RepoRoot "config\settings.example.yml"))) {
    Copy-Item -LiteralPath (Join-Path $RepoRoot "config\settings.example.yml") -Destination (Join-Path $Root "config\settings.yml")
    $Secret = (& $RuntimePythonResolved -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
    $SettingsPath = Join-Path $Root "config\settings.yml"
    $SettingsText = Get-Content -LiteralPath $SettingsPath -Raw
    $SettingsText = $SettingsText.Replace("CHANGE_ME_GENERATE_WITH_SECRETS_TOKEN_URLSAFE", $Secret)
    Set-Content -LiteralPath $SettingsPath -Value $SettingsText -Encoding UTF8
    Write-Host "Created config\settings.yml from example and generated a local secret_key."
}

Set-Location $Root

if (!(Test-Path $Repo)) {
    try {
        git clone --depth 1 https://github.com/searxng/searxng.git searxng
    } catch {
        Write-Host "git clone failed, downloading source archive..."
        Invoke-WebRequest -Uri "https://github.com/searxng/searxng/archive/refs/heads/master.zip" -OutFile $Zip
        Remove-Item -LiteralPath $Extract -Recurse -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Path $Extract | Out-Null
        tar -xf $Zip -C $Extract
        Move-Item -LiteralPath (Join-Path $Extract "searxng-master") -Destination $Repo
        Remove-Item -LiteralPath $Extract -Recurse -Force
    }
}

if (!(Test-Path $Python)) {
    & $RuntimePythonResolved -m venv $Venv
}

& $Python -m pip install -U pip setuptools wheel

Set-Location $Repo

& $Python -m pip install -r requirements.txt
$ApiPoolRequirements = Join-Path $Root "api_pool\requirements.txt"
if (Test-Path $ApiPoolRequirements) {
    & $Python -m pip install -r $ApiPoolRequirements
}
& $Python -m pip install -e .
if ($LASTEXITCODE -ne 0) {
    Write-Host "Editable install failed with build isolation; retrying without build isolation."
    & $Python -m pip install --no-build-isolation -e .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Editable install failed."
        exit $LASTEXITCODE
    }
}

& powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptRoot "apply-windows-patch.ps1") -Root $Root

Write-Host ""
Write-Host "Install finished."
Write-Host "Create config\settings.yml from config\settings.example.yml if needed."
Write-Host "Then double-click: $Root\start-searxng.cmd"
Write-Host "PowerShell alternative: powershell -ExecutionPolicy Bypass -File $Root\scripts\start.ps1"
