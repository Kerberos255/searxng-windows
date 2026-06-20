param(
    [string]$Url = "http://127.0.0.1:8888/search?q=test&format=json&categories=general"
)

$ErrorActionPreference = "Stop"

try {
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 30
    Write-Host "HTTP status:" $r.StatusCode

    if ($r.Content -match '"query"') {
        Write-Host "SearXNG JSON search works."
    } else {
        Write-Host "Response received, but JSON content may be unexpected."
        Write-Host $r.Content.Substring(0, [Math]::Min(500, $r.Content.Length))
    }
} catch {
    Write-Host "Check failed:"
    Write-Host $_
    exit 1
}
