param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows",
    [string]$BrokerUrl = "http://127.0.0.1:8890",
    [string]$SearxngUrl = "http://127.0.0.1:8888",
    [switch]$LiveSearch
)

$ErrorActionPreference = "Stop"
$AllOk = $true

try {
    $Root = [System.IO.Path]::GetFullPath($Root)
    $ApiPoolHelper = [System.IO.Path]::Combine($Root, "scripts\api-pool.ps1")
} catch {
    Write-Host "Invalid installation root path: $Root"
    Write-Host $_
    exit 1
}

if (![System.IO.File]::Exists($ApiPoolHelper)) {
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
    } catch {
        Write-Host "Broker health check failed:" $_
        $AllOk = $false
    }
} else {
    Write-Host "API Pool is disabled; Broker checks skipped."
}

try {
    $Response = Invoke-WebRequest -Uri "$SearxngUrl/" -UseBasicParsing -TimeoutSec 5
    if ($Response.StatusCode -ne 200) {
        Write-Host "SearXNG homepage returned HTTP $($Response.StatusCode)."
        $AllOk = $false
    } else {
        Write-Host "SearXNG homepage: HTTP 200"
    }
} catch {
    Write-Host "SearXNG health check failed:" $_
    $AllOk = $false
}

if ($LiveSearch) {
    try {
        $Encoded = [uri]::EscapeDataString("open source metasearch")
        if ($ApiPoolEnabled) {
            $SearchUrl = "$BrokerUrl/search?q=$Encoded&format=json&count=3"
        } else {
            $SearchUrl = "$SearxngUrl/search?q=$Encoded&format=json&categories=general"
        }
        $Search = Invoke-RestMethod -Uri $SearchUrl -Method Get -TimeoutSec 30
        $ResultCount = if ($null -eq $Search.results) { 0 } else { @($Search.results).Count }
        Write-Host "Live search results:" $ResultCount "provider:" $Search.provider "fallback:" $Search.fallback_used
        if ($ResultCount -le 0) { $AllOk = $false }
    } catch {
        Write-Host "Live search failed:" $_
        $AllOk = $false
    }
} else {
    Write-Host "Live search skipped. Use -LiveSearch to call upstream providers/search engines."
}

if ($AllOk) {
    Write-Host "All checks passed."
    exit 0
}
Write-Host "Some checks failed."
exit 1
