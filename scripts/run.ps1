param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows",
    [string]$ProxyUrl = "http://127.0.0.1:10808"
)

$ErrorActionPreference = "Stop"

$Searxng = Join-Path $Root "searxng"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Settings = Join-Path $Root "config\settings.yml"

if (!(Test-Path $VenvPython)) {
    Write-Host "Python venv not found: $VenvPython"
    exit 1
}

if (!(Test-Path $Settings)) {
    Write-Host "settings.yml not found: $Settings"
    exit 1
}

$env:SEARXNG_SETTINGS_PATH = $Settings
$env:PYTHONUTF8 = "1"
$env:HTTP_PROXY = $ProxyUrl
$env:HTTPS_PROXY = $ProxyUrl
$env:ALL_PROXY = $ProxyUrl
$env:http_proxy = $ProxyUrl
$env:https_proxy = $ProxyUrl
$env:all_proxy = $ProxyUrl
$env:NO_PROXY = "127.0.0.1,localhost"
$env:no_proxy = "127.0.0.1,localhost"

Set-Location $Searxng

Write-Host "Starting SearXNG on http://127.0.0.1:8888 ..."
& $VenvPython "searx\webapp.py"
