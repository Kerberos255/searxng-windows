param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows",
    [string]$BrokerUrl = "http://127.0.0.1:8890",
    [string]$SearxngUrl = "http://127.0.0.1:8888"
)

$ErrorActionPreference = "Stop"
$AllOk = $true

$ApiPoolHelper = Join-Path $Root "scripts\api-pool.ps1"
if (!(Test-Path $ApiPoolHelper)) {
    Write-Host "API Pool helper not found: $ApiPoolHelper"
    exit 1
}
. $ApiPoolHelper
$ApiPoolEnabled = Test-ApiPoolEnabled -Root $Root

if ($ApiPoolEnabled) {
    try {
        $Health = Invoke-RestMethod -Uri "$BrokerUrl/health" -Method Get -TimeoutSec 5
        Write-Host "Broker health:" $Health.status "providers:" $Health.providers_tracked
        if ($Health.status -ne "ok") { $AllOk = $false }

        $Status = Invoke-RestMethod -Uri "$BrokerUrl/status" -Method Get -TimeoutSec 5
        Write-Host "API priority:" ($Status.priority_order -join " -> ")
        foreach ($Provider in $Status.providers) {
            Write-Host " - $($Provider.provider): configured=$($Provider.configured), status=$($Provider.status)"
        }

        $BrokerQuery = [uri]::EscapeDataString("open source metasearch")
        $BrokerSearch = Invoke-RestMethod `
            -Uri "$BrokerUrl/search?q=$BrokerQuery&format=json&count=3" `
            -Method Get `
            -TimeoutSec 60
        $BrokerResults = @($BrokerSearch.results).Count
        Write-Host "API-first gateway works; provider=$($BrokerSearch.provider), fallback=$($BrokerSearch.fallback_used), results=$BrokerResults"
        if ($BrokerResults -le 0) { $AllOk = $false }
    } catch {
        Write-Host "Broker check failed:" $_
        $AllOk = $false
    }
} else {
    Write-Host "API Pool is disabled; Broker checks skipped."
}

try {
    $Encoded = [uri]::EscapeDataString("open source metasearch")
    $Response = Invoke-RestMethod `
        -Uri "$SearxngUrl/search?q=$Encoded&format=json&categories=general" `
        -Method Get `
        -TimeoutSec 30
    $ResultCount = @($Response.results).Count
    Write-Host "SearXNG results:" $ResultCount
    if ($ResultCount -le 0) {
        Write-Host "SearXNG responded but returned no free-web results."
        $AllOk = $false
    }
} catch {
    Write-Host "SearXNG check failed:" $_
    $AllOk = $false
}

if ($AllOk) {
    Write-Host "All checks passed."
    exit 0
}
Write-Host "Some checks failed."
exit 1
