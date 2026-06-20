param(
    [string]$Root = "E:\openclaw\searxng_windows",
    [string]$RuntimePython = "E:\openclaw\runtime\python\python.exe"
)

$ErrorActionPreference = "Stop"

$Repo = Join-Path $Root "searxng"
$Zip = Join-Path $Root "searxng-master.zip"
$Extract = Join-Path $Root "_extract"
$Venv = Join-Path $Root ".venv"
$Python = Join-Path $Venv "Scripts\python.exe"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot

if (!(Test-Path $RuntimePython)) {
    Write-Host "Runtime Python not found: $RuntimePython"
    exit 1
}

New-Item -ItemType Directory -Force -Path $Root | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Root "scripts"),(Join-Path $Root "config") | Out-Null

if ((Resolve-Path -LiteralPath $ScriptRoot).Path -ne (Resolve-Path -LiteralPath (Join-Path $Root "scripts")).Path) {
    Copy-Item -LiteralPath (Join-Path $ScriptRoot "*") -Destination (Join-Path $Root "scripts") -Recurse -Force
}

if (!(Test-Path (Join-Path $Root "config\settings.yml")) -and (Test-Path (Join-Path $RepoRoot "config\settings.example.yml"))) {
    Copy-Item -LiteralPath (Join-Path $RepoRoot "config\settings.example.yml") -Destination (Join-Path $Root "config\settings.yml")
    $Secret = (& $RuntimePython -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
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
    & $RuntimePython -m venv $Venv
}

& $Python -m pip install -U pip setuptools wheel

Set-Location $Repo

& $Python -m pip install -r requirements.txt
& $Python -m pip install --no-build-isolation -e .

& powershell -ExecutionPolicy Bypass -File (Join-Path $ScriptRoot "apply-windows-patch.ps1") -Root $Root

Write-Host ""
Write-Host "Install finished."
Write-Host "Create config\settings.yml from config\settings.example.yml if needed."
Write-Host "Then run: powershell -ExecutionPolicy Bypass -File $Root\scripts\start.ps1"
