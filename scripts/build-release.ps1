param(
    [Parameter(Mandatory = $true)]
    [string]$Tag,
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

if ($Tag -notmatch '^v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$') {
    throw "Tag must use semantic version format, for example v0.2.0."
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
if (![System.IO.Path]::IsPathRooted($OutputDir)) {
    $OutputDir = Join-Path $RepoRoot $OutputDir
}

Remove-Item -LiteralPath $OutputDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Copy-Item -LiteralPath (Join-Path $RepoRoot "install-searxng-windows.cmd") -Destination $OutputDir
Copy-Item -LiteralPath (Join-Path $RepoRoot "install-searxng-windows.ps1") -Destination $OutputDir

$ZipName = "searxng-windows-$Tag.zip"
$ZipPath = Join-Path $OutputDir $ZipName
Push-Location $RepoRoot
try {
    git archive --format=zip --output=$ZipPath --prefix="searxng-windows-$Tag/" HEAD
    if ($LASTEXITCODE -ne 0) {
        throw "git archive failed."
    }
} finally {
    Pop-Location
}

$ChecksumPath = Join-Path $OutputDir "SHA256SUMS.txt"
Get-ChildItem $OutputDir -File |
    Where-Object { $_.Name -ne "SHA256SUMS.txt" } |
    Sort-Object Name |
    ForEach-Object {
        $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        "$Hash  $($_.Name)"
    } | Set-Content -LiteralPath $ChecksumPath -Encoding ASCII

$Expected = @(
    "install-searxng-windows.cmd",
    "install-searxng-windows.ps1",
    $ZipName,
    "SHA256SUMS.txt"
)
foreach ($Name in $Expected) {
    $Path = Join-Path $OutputDir $Name
    if (!(Test-Path $Path) -or (Get-Item $Path).Length -le 0) {
        throw "Missing or empty release asset: $Name"
    }
}

Write-Host "Release assets built in: $OutputDir"
Get-ChildItem $OutputDir | Format-Table Name, Length
Get-Content $ChecksumPath
