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

# Offline HTML-template integrity check. Homepage 200 alone cannot catch this failure.
$WebappFile = [IO.Path]::Combine($Root, "searxng\searx\webapp.py")
$DefaultTemplate = [IO.Path]::Combine($Root, "searxng\searx\templates\simple\result_templates\default.html")
if (![IO.File]::Exists($WebappFile) -or ![IO.File]::Exists($DefaultTemplate)) {
    Write-Host "HTML result-template files are missing."
    $AllOk = $false
} elseif (!(Select-String -LiteralPath $WebappFile -SimpleMatch -Pattern 'result_templates = {name.replace(os.sep, "/")' -Quiet)) {
    Write-Host "Windows HTML result-template patch missing; reinstall using the latest installer."
    $AllOk = $false
} else {
    Write-Host "HTML result-template routing: OK"
}

# Default search priority hook must be installed for API-first routing.
if ([IO.File]::Exists($WebappFile) -and
    !(Select-String -LiteralPath $WebappFile -SimpleMatch -Pattern 'apply_default_search_priority(search_query, raw_text_query, sxng_request.form)' -Quiet)) {
    Write-Host "Default API-first search routing patch is missing."
    $AllOk = $false
}
# Verify CSS/JS links will resolve to their actual theme assets on Windows.
$StaticCss = [IO.Path]::Combine($Root, "searxng\searx\static\themes\simple\sxng-ltr.min.css")
if (![IO.File]::Exists($StaticCss) -or
    !(Select-String -LiteralPath $WebappFile -SimpleMatch -Pattern '_STATIC_FILES = [name.replace(os.sep, "/")' -Quiet)) {
    Write-Host "Windows static URL routing patch missing."
    $AllOk = $false
}

# Validate actual CSS/JS URLs referenced by the rendered homepage (no API cost).
try {
    $Page = Invoke-WebRequest -Uri "$SearxngUrl/" -UseBasicParsing -TimeoutSec 5
    foreach ($Asset in @(
        "/static/themes/simple/sxng-ltr.min.css",
        "/static/themes/simple/sxng-core.min.js",
        "/static/themes/simple/img/favicon.svg"
    )) {
        if (!$Page.Content.Contains($Asset)) {
            Write-Host "Homepage does not reference expected static asset: $Asset"
            $AllOk = $false
            continue
        }
        $AssetReply = Invoke-WebRequest -Uri "$SearxngUrl$Asset" -UseBasicParsing -TimeoutSec 5
        if ($AssetReply.StatusCode -ne 200) {
            Write-Host "Static asset failed: $Asset HTTP $($AssetReply.StatusCode)"
            $AllOk = $false
        }
    }
    if ($AllOk) { Write-Host "Homepage CSS, JS and favicon URLs: HTTP 200" }
} catch {
    Write-Host "Static asset health check failed:" $_
    $AllOk = $false
}

if ($AllOk) {
    Write-Host "All checks passed."
    exit 0
}
Write-Host "Some checks failed."
exit 1
