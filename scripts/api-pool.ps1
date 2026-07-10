function Test-ApiPoolEnabled {
    param(
        [string]$Root = "$env:USERPROFILE\Apps\searxng-windows"
    )

    $SettingsPath = Join-Path $Root "config\settings.yml"
    if (!(Test-Path $SettingsPath)) {
        return $false
    }

    $InsideApiPool = $false
    foreach ($RawLine in Get-Content -LiteralPath $SettingsPath) {
        $Line = $RawLine.Trim()
        $NormalizedLine = $Line.Replace('"', '').Replace("'", '')

        if ($NormalizedLine -eq "- name: api pool") {
            $InsideApiPool = $true
            continue
        }

        if ($InsideApiPool -and $NormalizedLine.StartsWith("- name:")) {
            break
        }

        if ($InsideApiPool -and $Line -match '^disabled:\s*(true|false)\s*$') {
            return $Matches[1].ToLowerInvariant() -eq "false"
        }
    }

    return $false
}
