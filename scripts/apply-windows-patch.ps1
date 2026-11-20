param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows"
)

$ErrorActionPreference = "Stop"

$ValkeyDb = Join-Path $Root "searxng\searx\valkeydb.py"

if (!(Test-Path $ValkeyDb)) {
    Write-Host "valkeydb.py not found: $ValkeyDb"
    exit 1
}

$Text = Get-Content -LiteralPath $ValkeyDb -Raw

$OptionalPwdImport = @'
try:
    import pwd
except ImportError:
    pwd = None
'@

$Text = $Text -replace '(?m)^import pwd\s*$', $OptionalPwdImport

$Pattern = '(?s)\s*_pw = pwd\.getpwuid\(os\.getuid\(\)\)\s*logger\.exception\("\[%s \(%s\)\] can''t connect valkey DB \.\.\.", _pw\.pw_name, _pw\.pw_uid\)'
$Replacement = @'

        if pwd is not None:
            _pw = pwd.getpwuid(os.getuid())
            user_name, user_id = _pw.pw_name, _pw.pw_uid
        else:
            user_name, user_id = os.environ.get("USERNAME", "unknown"), os.getpid()
        logger.exception("[%s (%s)] can't connect valkey DB ...", user_name, user_id)
'@

$Text = [regex]::Replace($Text, $Pattern, $Replacement)

$AlreadyPatchedPattern = '(?s)\s*if pwd:\s*_pw = pwd\.getpwuid\(os\.getuid\(\)\)\s*user_name, user_id = _pw\.pw_name, _pw\.pw_uid\s*else:\s*user_name, user_id = os\.environ\.get\(''USERNAME'', ''unknown''\), os\.getpid\(\)\s*logger\.exception\("\[%s \(%s\)\] can''t connect valkey DB \.\.\.", user_name, user_id\)'
$NormalizedReplacement = @'

        if pwd:
            _pw = pwd.getpwuid(os.getuid())
            user_name, user_id = _pw.pw_name, _pw.pw_uid
        else:
            user_name, user_id = os.environ.get('USERNAME', 'unknown'), os.getpid()
        logger.exception("[%s (%s)] can't connect valkey DB ...", user_name, user_id)
'@

$Text = [regex]::Replace($Text, $AlreadyPatchedPattern, $NormalizedReplacement)

Set-Content -LiteralPath $ValkeyDb -Value $Text -Encoding UTF8

$Patched = Get-Content -LiteralPath $ValkeyDb -Raw

if ($Patched -match '(?m)^import pwd\s*$') {
    Write-Host "Patch failed: bare import pwd still exists."
    exit 1
}

if ($Patched -notmatch 'except ImportError:\s*\r?\n\s*pwd = None') {
    Write-Host "Patch failed: optional pwd fallback not found."
    exit 1
}

if ($Patched -match 'pwd\.getpwuid\(os\.getuid\(\)\).*_pw\.pw_name, _pw\.pw_uid' -and $Patched -notmatch 'if pwd is not None|if pwd:') {
    Write-Host "Patch failed: Unix-only pwd logging block still appears unguarded."
    exit 1
}

Write-Host "Windows compatibility patch applied."


$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptRoot
$ApiPoolPatch = Join-Path $RepoRoot "patches\api_pool.py"
$ApiPoolTarget = Join-Path $Root "searxng\searx\engines\api_pool.py"

if (!(Test-Path $ApiPoolPatch)) {
    Write-Host "API Pool engine patch not found: $ApiPoolPatch"
    exit 1
}

Copy-Item -LiteralPath $ApiPoolPatch -Destination $ApiPoolTarget -Force
if (!(Test-Path $ApiPoolTarget)) {
    Write-Host "API Pool engine installation failed: $ApiPoolTarget"
    exit 1
}

Write-Host "API Pool SearXNG engine installed."

# Keep engines without native time-range support searchable without a date filter.
$TimeRangePatchScript = Join-Path $ScriptRoot "patch_time_range_engines.py"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (!(Test-Path -LiteralPath $TimeRangePatchScript -PathType Leaf) -or
    !(Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw "Date fallback patch prerequisites are missing."
}
& $VenvPython $TimeRangePatchScript $Root
if ($LASTEXITCODE -ne 0) {
    throw "Date fallback patch failed."
}

# Normalize Windows HTML result template registry keys for Jinja.
$ResultTemplatePatch = Join-Path $ScriptRoot "patch_result_templates.py"
if (![System.IO.File]::Exists($ResultTemplatePatch)) {
    throw "Windows result-template patch script is missing: $ResultTemplatePatch"
}
& $VenvPython $ResultTemplatePatch $Root
if ($LASTEXITCODE -ne 0) {
    throw "Windows result-template patch failed."
}

# Route default web searches to the API Pool only when provider credentials exist.
$DefaultSearchPatch = Join-Path $ScriptRoot "patch_default_search_priority.py"
if (![IO.File]::Exists($DefaultSearchPatch)) {
    throw "Default search priority patch script is missing."
}
& $VenvPython $DefaultSearchPatch $Root
if ($LASTEXITCODE -ne 0) {
    throw "Default search priority patch failed."
}

# Fix Windows paths in the CSS/JS/image registry for the simple theme.
$StaticUrlPatch = Join-Path $ScriptRoot "patch_static_urls.py"
if (![IO.File]::Exists($StaticUrlPatch)) { throw "Windows static URL patch script missing." }
& $VenvPython $StaticUrlPatch $Root
if ($LASTEXITCODE -ne 0) { throw "Windows static URL patch failed." }
