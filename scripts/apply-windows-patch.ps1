param(
    [string]$Root = "E:\openclaw\searxng_windows"
)

$ErrorActionPreference = "Stop"

$ValkeyDb = Join-Path $Root "searxng\searx\valkeydb.py"

if (!(Test-Path $ValkeyDb)) {
    Write-Host "valkeydb.py not found: $ValkeyDb"
    exit 1
}

$Text = Get-Content -LiteralPath $ValkeyDb -Raw

if ($Text -notmatch "except ImportError:\s*\r?\n\s+pwd = None") {
    $Text = $Text.Replace(
        "import os`r`nimport pwd`r`nimport logging",
        "import os`r`nimport logging"
    )
    $Text = $Text.Replace(
        "import valkey`r`nfrom searx import get_setting",
        "import valkey`r`nfrom searx import get_setting`r`n`r`ntry:`r`n    import pwd`r`nexcept ImportError:`r`n    pwd = None"
    )
}

$OldBlock = @'
        _pw = pwd.getpwuid(os.getuid())
        logger.exception("[%s (%s)] can't connect valkey DB ...", _pw.pw_name, _pw.pw_uid)
'@

$NewBlock = @'
        if pwd:
            _pw = pwd.getpwuid(os.getuid())
            user_name, user_id = _pw.pw_name, _pw.pw_uid
        else:
            user_name, user_id = os.environ.get('USERNAME', 'unknown'), os.getpid()
        logger.exception("[%s (%s)] can't connect valkey DB ...", user_name, user_id)
'@

if ($Text.Contains($OldBlock)) {
    $Text = $Text.Replace($OldBlock, $NewBlock)
}

Set-Content -LiteralPath $ValkeyDb -Value $Text -Encoding UTF8
Write-Host "Windows compatibility patch applied."
