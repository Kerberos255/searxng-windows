param(
    [Parameter(Mandatory=$true)][string]$Ref,
    [Parameter(Mandatory=$true)][string]$RuntimePython,
    [switch]$Extended
)
$ErrorActionPreference = "Stop"
$InstallRoot = Join-Path $env:RUNNER_TEMP ("searxng smoke with spaces " + [guid]::NewGuid().ToString("N"))
$InstallerFolder = Join-Path $env:RUNNER_TEMP ("downloaded installer " + [guid]::NewGuid().ToString("N"))
$PreviousCI = $env:CI
$env:CI = "true"

function Invoke-Launcher {
    param([string]$File, [string[]]$Arguments = @())
    & (Join-Path $InstallRoot $File) @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File failed (exit $LASTEXITCODE)." }
}

function Assert-Http {
    param([string]$Uri)
    $Response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 25
    if ($Response.StatusCode -ne 200) { throw "$Uri returned HTTP $($Response.StatusCode)." }
}

function Assert-Settings {
    param([string]$Expected)
    $Actual = [IO.File]::ReadAllText((Join-Path $InstallRoot "config\settings.yml"))
    if ($Actual -cne $Expected) { throw "Installer or updater unexpectedly changed settings.yml." }
}

function Invoke-Bootstrap {
    $Launcher = Join-Path $InstallerFolder "install-searxng-windows.cmd"
    & $Launcher -Root $InstallRoot -RuntimePython $RuntimePython -Ref $Ref
    if ($LASTEXITCODE -ne 0) { throw "Downloaded CMD bootstrap failed ($LASTEXITCODE)." }
}

try {
    if ($Ref -notmatch '^[0-9a-fA-F]{40}$') { throw "Smoke tests require an immutable Git SHA." }
    New-Item -ItemType Directory -Force -Path $InstallerFolder | Out-Null

    # Both installer entry points are fetched from GitHub, not taken from the checkout.
    $BaseUrl = "https://raw.githubusercontent.com/Kerberos255/searxng-windows/$Ref"
    foreach ($Name in @("install-searxng-windows.cmd", "install-searxng-windows.ps1")) {
        Invoke-WebRequest -Uri "$BaseUrl/$Name" -OutFile (Join-Path $InstallerFolder $Name) -UseBasicParsing
    }
    Write-Host "GitHub bootstrap downloaded from commit $Ref"
    Invoke-Bootstrap

    $InstalledLauncher = Join-Path $InstallRoot "scripts\start.ps1"
    if (![IO.File]::Exists($InstalledLauncher)) { throw "Bootstrap did not install start.ps1." }
    $Expected = [IO.File]::ReadAllText((Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\start.ps1")).Replace(([string][char]13+[char]10),[string][char]10)
    $Installed = [IO.File]::ReadAllText($InstalledLauncher).Replace(([string][char]13+[char]10),[string][char]10)
    if ($Installed -cne $Expected) { throw "Bootstrap installed a different commit than the PR." }

    $Settings = [IO.File]::ReadAllText((Join-Path $InstallRoot "config\settings.yml"))
    Invoke-Launcher "start-searxng.cmd"
    Invoke-Launcher "check-searxng.cmd"
    Assert-Http "http://127.0.0.1:8888/"
    Invoke-Launcher "stop-searxng.cmd"
    Write-Host "PASS downloaded CMD bootstrap -> installation -> 8888 HTTP 200 -> check -> stop"

    if ($Extended) {
        Invoke-Bootstrap
        Assert-Settings $Settings
        Write-Host "PASS bootstrap reinstall preserves config"

        # Start both services without requiring paid API keys or spending API credits.
        $SettingsPath = Join-Path $InstallRoot "config\settings.yml"
        $Pattern = '(?m)(- name: api pool\s*\r?\n\s*engine: api_pool\s*\r?\n\s*disabled:\s*)true'
        if ([regex]::Matches($Settings, $Pattern).Count -ne 1) { throw "Expected exactly one disabled API Pool engine." }
        $EnabledSettings = [regex]::Replace($Settings, $Pattern, '$' + '{1}false')
        [IO.File]::WriteAllText($SettingsPath, $EnabledSettings, (New-Object Text.UTF8Encoding($false)))
        Invoke-Launcher "start-searxng.cmd"
        Invoke-Launcher "check-searxng.cmd"
        Assert-Http "http://127.0.0.1:8888/"
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1:8890/health" -TimeoutSec 12
        if ($Health.status -ne "ok") { throw "API Pool broker did not become healthy." }

        # No provider keys: the public broker must return the free-search fallback path.
        $Fallback = Invoke-RestMethod -Uri "http://127.0.0.1:8890/search?q=windows-smoke&format=json&count=1" -TimeoutSec 42
        if ($Fallback.fallback_used -ne $true) { throw "API Pool did not activate free search fallback." }
        if ($null -eq $Fallback.results) { throw "API Pool fallback returned no results array." }
        Write-Host "PASS 8888 + 8890, no-key fallback path, and both health checks"

        # Force failure after staged source replacement; previous source must be restored.
        $OriginalWebapp = Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $InstallRoot "searxng\searx\webapp.py")
        $PatchPath = Join-Path $InstallRoot "scripts\apply-windows-patch.ps1"
        $PatchContent = [IO.File]::ReadAllText($PatchPath)
        $UpdatePath = Join-Path $InstallRoot "scripts\update.ps1"
        $UpdateContent = [IO.File]::ReadAllText($UpdatePath)
        $ArchivePath = Join-Path $InstallRoot "searxng-master.zip"
        if (![IO.File]::Exists($ArchivePath)) { throw "Cached upstream source archive not found." }
        $DownloadCommand = 'Invoke-WebRequest -Uri "https://github.com/searxng/searxng/archive/refs/heads/master.zip" -OutFile $DownloadZip -UseBasicParsing'
        $LocalCommand = 'Copy-Item -LiteralPath (Join-Path $Root "searxng-master.zip") -Destination $DownloadZip -Force'
        if (!$UpdateContent.Contains($DownloadCommand)) { throw "Update script download command changed." }
        $TestUpdate = $UpdateContent.Replace($DownloadCommand, $LocalCommand)
        try {
            [IO.File]::WriteAllText($PatchPath, "Write-Host 'Injected smoke-only update failure'; exit 29")
            [IO.File]::WriteAllText($UpdatePath, $TestUpdate)
            $OldPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $UpdatePath -Root $InstallRoot 1>$null 2>$null
                $FailureExit = $LASTEXITCODE
            } finally {
                $ErrorActionPreference = $OldPreference
            }
        } finally {
            [IO.File]::WriteAllText($PatchPath, $PatchContent, (New-Object Text.UTF8Encoding($false)))
            [IO.File]::WriteAllText($UpdatePath, $UpdateContent, (New-Object Text.UTF8Encoding($false)))
        }
        if ($FailureExit -eq 0) { throw "Injected update failure unexpectedly succeeded." }
        $AfterWebapp = Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $InstallRoot "searxng\searx\webapp.py")
        if ($AfterWebapp.Hash -ne $OriginalWebapp.Hash) { throw "Failed update did not restore original webapp.py." }
        Assert-Settings $EnabledSettings
        Invoke-Launcher "start-searxng.cmd"
        Invoke-Launcher "check-searxng.cmd"
        Write-Host "PASS failure-injected update restores source, settings and services"
        Invoke-Launcher "stop-searxng.cmd"
    }
    Write-Host "PASS GitHub bootstrap smoke: $Ref"
} finally {
    $env:CI = $PreviousCI
    if ([IO.File]::Exists((Join-Path $InstallRoot "scripts\stop.ps1"))) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallRoot "scripts\stop.ps1") -Root $InstallRoot
    }
}
