param(
    [string]$BrokerUrl = "http://127.0.0.1:8890",
    [string]$SearxngUrl = "http://127.0.0.1:8888"
)

$ErrorActionPreference = "Stop"
$AllOk = $true

try {
    $Health = Invoke-RestMethod -Uri "$BrokerUrl/health" -Method Get -TimeoutSec 5
    Write-Host "Broker health:" $Health.status "providers:" $Health.providers_tracked
    if ($Health.status -ne "ok") { $AllOk = $false }

    $Status = Invoke-RestMethod -Uri "$BrokerUrl/status" -Method Get -TimeoutSec 5
    Write-Host "API priority:" ($Status.priority_order -join " -> ")
    foreach ($Provider in $Status.providers) {
        Write-Host " - $($Provider.provider): configured=$($Provider.configured), status=$($Provider.status)"
    }

    $BrokerBody = @{
        query = "open source metasearch"
        max_results = 3
    } | ConvertTo-Json
    $BrokerSearch = Invoke-RestMethod `
        -Uri "$BrokerUrl/search" `
        -Method Post `
        -ContentType "application/json" `
        -Body $BrokerBody `
        -TimeoutSec 30
    $BrokerResults = @($BrokerSearch.results).Count
    Write-Host "Broker search structure works; provider=$($BrokerSearch.provider), results=$BrokerResults"
} catch {
    Write-Host "Broker check failed:" $_
    $AllOk = $false
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
