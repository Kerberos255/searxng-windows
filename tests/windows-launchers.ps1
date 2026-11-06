# Regression tests for Windows PowerShell 5.1 and CMD launchers.
$ErrorActionPreference = "Stop"
$SourceRoot = Split-Path -Parent $PSScriptRoot
$Fixture = Join-Path ([IO.Path]::GetTempPath()) ("searxng spaces 中文 " + [guid]::NewGuid().ToString("N"))
$PreviousCI = $env:CI
$env:CI = "true"

function Assert-Launch {
    param([string]$Name, [int]$Code, [string]$Message)
    $SavedPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $Output = (& (Join-Path $Fixture $Name) 2>&1 | Out-String)
        $ExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $SavedPreference
    }
    if ($ExitCode -ne $Code -or !$Output.Contains($Message)) {
        throw "$Name returned $ExitCode (expected $Code): $Output"
    }
    if ($Output -match "Illegales Zeichen|Illegal characters") {
        throw "$Name still raises an invalid-path error: $Output"
    }
    Write-Host "PASS $Name [$Message]"
}

try {
    New-Item -ItemType Directory -Force -Path (Join-Path $Fixture "scripts"), (Join-Path $Fixture "config") | Out-Null
    foreach ($Name in @("start-searxng.cmd", "check-searxng.cmd", "stop-searxng.cmd")) {
        Copy-Item -LiteralPath (Join-Path $SourceRoot $Name) -Destination (Join-Path $Fixture $Name)
    }
    foreach ($Name in @("start.ps1", "check.ps1", "stop.ps1")) {
        Copy-Item -LiteralPath (Join-Path $SourceRoot "scripts\$Name") -Destination (Join-Path $Fixture "scripts\$Name")
    }
    Assert-Launch "start-searxng.cmd" 1 "API Pool helper not found:"
    Assert-Launch "check-searxng.cmd" 1 "API Pool helper not found:"
    Assert-Launch "stop-searxng.cmd" 0 "No verified SearXNG or API Pool processes were stopped."

    Copy-Item -LiteralPath (Join-Path $SourceRoot "scripts\api-pool.ps1") -Destination (Join-Path $Fixture "scripts\api-pool.ps1")
    [IO.File]::WriteAllText((Join-Path $Fixture "config\settings.yml"), "engines:`r`n  - name: api pool`r`n    disabled: true`r`n")
    $FakeRun = @'
param([string]$Root)
[IO.File]::WriteAllText((Join-Path $Root "child-root.txt"), $Root)
'@
    [IO.File]::WriteAllText((Join-Path $Fixture "scripts\run.ps1"), $FakeRun)

    # Use an unused local port so an existing developer SearXNG at 8888 cannot bypass the child.
    $Listener = New-Object System.Net.Sockets.TcpListener([Net.IPAddress]::Loopback, 0)
    $Listener.Start()
    $UnusedPort = $Listener.LocalEndpoint.Port
    $Listener.Stop()
    $StartFile = Join-Path $Fixture "scripts\start.ps1"
    $StartText = [IO.File]::ReadAllText($StartFile)
    $StartText = $StartText.Replace("http://127.0.0.1:8888/", "http://127.0.0.1:$UnusedPort/")
    [IO.File]::WriteAllText($StartFile, $StartText)

    # The fake child exits without listening: startup should fail after writing the captured argument.
    Assert-Launch "start-searxng.cmd" 1 "SearXNG did not respond"
    $Captured = Join-Path $Fixture "child-root.txt"
    if (![IO.File]::Exists($Captured)) {
        $Err = Join-Path $Fixture "searxng-run.err.log"
        $Details = if ([IO.File]::Exists($Err)) { [IO.File]::ReadAllText($Err) } else { "No stderr log" }
        throw "Child process did not receive Root: $Details"
    }
    $Actual = [IO.Path]::GetFullPath([IO.File]::ReadAllText($Captured)).TrimEnd('\')
    $Expected = [IO.Path]::GetFullPath($Fixture).TrimEnd('\')
    if (![string]::Equals($Actual, $Expected, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Corrupt argument in child: expected '$Expected', got '$Actual'"
    }
    Write-Host "PASS native child argument quoting with spaces and Unicode."
} finally {
    $env:CI = $PreviousCI
    if ([IO.Directory]::Exists($Fixture)) {
        Remove-Item -LiteralPath $Fixture -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Expected negative-case launcher exits must not fail the enclosing CI step.
$global:LASTEXITCODE = 0
