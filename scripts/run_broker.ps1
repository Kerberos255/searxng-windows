param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows",
    [string]$ProxyUrl = "",
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Broker = Join-Path $Root "api_pool\app.py"

if (!(Test-Path $Python)) {
    Write-Host "Python venv not found: $Python"
    exit 1
}
if (!(Test-Path $Broker)) {
    Write-Host "API Pool Broker not found: $Broker"
    exit 1
}

if (!$EnvFile) {
    $EnvFile = Join-Path $Root "config\api-pool.env"
}
$env:API_POOL_ENV_FILE = $EnvFile
$env:PYTHONUTF8 = "1"

if ($ProxyUrl) {
    $env:HTTP_PROXY = $ProxyUrl
    $env:HTTPS_PROXY = $ProxyUrl
    $env:ALL_PROXY = $ProxyUrl
    $env:http_proxy = $ProxyUrl
    $env:https_proxy = $ProxyUrl
    $env:all_proxy = $ProxyUrl
}
$env:NO_PROXY = "127.0.0.1,localhost"
$env:no_proxy = "127.0.0.1,localhost"

Set-Location $Root
Write-Host "Starting API Pool Broker on http://127.0.0.1:8890 ..."
& $Python $Broker
