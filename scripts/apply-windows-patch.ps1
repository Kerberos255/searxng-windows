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
