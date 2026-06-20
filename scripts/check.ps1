param(
    [string]$Url = "http://127.0.0.1:8888/search?q=openai&format=json&categories=general"
)

$ErrorActionPreference = "Stop"

try {
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 30
    Write-Host "HTTP status:" $r.StatusCode

    $data = $r.Content | ConvertFrom-Json
    $resultCount = if ($null -eq $data.results) { 0 } else { @($data.results).Count }

    Write-Host "Query:" $data.query
    Write-Host "Results:" $resultCount

    if ($data.unresponsive_engines) {
        Write-Host "Unresponsive engines:"
        $data.unresponsive_engines | ForEach-Object { Write-Host " -" $_ }
    }

    if ($resultCount -gt 0) {
        Write-Host "SearXNG JSON search works."
        exit 0
    } else {
        Write-Host "SearXNG responded, but no results were returned."
        exit 2
    }
} catch {
    Write-Host "Check failed:"
    Write-Host $_
    exit 1
}
