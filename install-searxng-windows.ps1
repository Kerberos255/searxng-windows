param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows",
    [string]$RuntimePython = "python",
    [string]$Repo = "Kerberos255/searxng-windows",
    [string]$Ref = "v0.1.0"
)

$ErrorActionPreference = "Stop"

$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("searxng-windows-install-" + [guid]::NewGuid().ToString("N"))
$ZipPath = Join-Path $TempRoot "searxng-windows.zip"
$ExtractPath = Join-Path $TempRoot "extract"

New-Item -ItemType Directory -Force -Path $TempRoot, $ExtractPath | Out-Null

try {
    $ArchiveUrl = "https://github.com/$Repo/archive/refs/tags/$Ref.zip"
    Write-Host "Downloading installer package: $ArchiveUrl"
    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $ZipPath -UseBasicParsing

    tar -xf $ZipPath -C $ExtractPath
    $PackageRoot = Get-ChildItem -LiteralPath $ExtractPath -Directory | Select-Object -First 1
    if (!$PackageRoot) {
        throw "Installer package did not contain an extracted directory."
    }

    $InstallScript = Join-Path $PackageRoot.FullName "scripts\install.ps1"
    if (!(Test-Path $InstallScript)) {
        throw "install.ps1 not found in installer package."
    }

    & powershell -ExecutionPolicy Bypass -File $InstallScript -Root $Root -RuntimePython $RuntimePython
} finally {
    Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
