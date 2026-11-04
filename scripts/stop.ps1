param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows"
)

$ErrorActionPreference = "Stop"

try {
    $RootFull = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
    $VenvPrefix = ([System.IO.Path]::GetFullPath((Join-Path $RootFull ".venv\Scripts"))).TrimEnd('\') + '\'
    $ExpectedBrokerApp = [System.IO.Path]::GetFullPath((Join-Path $RootFull "api_pool\app.py"))
    $ExpectedRunScript = [System.IO.Path]::GetFullPath((Join-Path $RootFull "scripts\run.ps1"))
    $ExpectedBrokerRunScript = [System.IO.Path]::GetFullPath((Join-Path $RootFull "scripts\run_broker.ps1"))
    $Processes = @(Get-CimInstance Win32_Process)
} catch {
    Write-Error "Unable to inspect SearXNG process identities: $_"
    exit 1
}

$ByPid = @{}
foreach ($Process in $Processes) {
    $ByPid[[int]$Process.ProcessId] = $Process
}

function Test-VerifiedProcess {
    param(
        [object]$Process,
        [hashtable]$ProcessMap
    )

    $Command = [string]$Process.CommandLine
    $Executable = [string]$Process.ExecutablePath
    if (!$Command -or !$Executable) {
        return $false
    }
    $IsShell = $Process.Name -in @("powershell.exe", "pwsh.exe")
    if ($IsShell) {
        $UsesFile = $Command -match '(?i)(?:^|\s)-File(?:\s|$)'
        return $UsesFile -and (
            $Command.IndexOf($ExpectedRunScript, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -or
            $Command.IndexOf($ExpectedBrokerRunScript, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        )
    }

    if ($Process.Name -notin @("python.exe", "pythonw.exe")) {
        return $false
    }

    # Windows venv launchers create a child running the base interpreter.
    # The child's ExecutablePath is outside .venv, but its parent is the venv stub.
    $Parent = $ProcessMap[[int]$Process.ParentProcessId]
    $ExeIsVenv = $Executable.StartsWith($VenvPrefix, [System.StringComparison]::OrdinalIgnoreCase)
    $ParentExe = if ($Parent) { [string]$Parent.ExecutablePath } else { "" }
    $ParentIsVenv = $ParentExe.StartsWith($VenvPrefix, [System.StringComparison]::OrdinalIgnoreCase)
    if (!$ExeIsVenv -and !$ParentIsVenv) {
        return $false
    }

    if ($Command.IndexOf($ExpectedBrokerApp, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
        return $true
    }

    if ($Command -match '(?i)searx[\\/]+webapp\.py') {
        # Relative webapp.py needs the installation's verified run.ps1 ancestor.
        $Ancestor = $Parent
        for ($Depth = 0; $Depth -lt 5 -and $Ancestor; $Depth++) {
            $AncestorCommand = [string]$Ancestor.CommandLine
            if (
                $Ancestor.Name -in @("powershell.exe", "pwsh.exe") -and
                $AncestorCommand.IndexOf($ExpectedRunScript, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
            ) {
                return $true
            }
            $Ancestor = $ProcessMap[[int]$Ancestor.ParentProcessId]
        }
    }
    return $false
}

$Targets = @(
    $Processes | Where-Object {
        $_.ProcessId -ne $PID -and
        (Test-VerifiedProcess -Process $_ -ProcessMap $ByPid)
    }
)
$TargetPids = @($Targets | ForEach-Object { [int]$_.ProcessId })

foreach ($Port in @(8888, 8890)) {
    $Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($Listener in $Listeners) {
        if ($TargetPids -notcontains [int]$Listener.OwningProcess) {
            Write-Warning "Port $Port belongs to an unverified process; it will be left untouched."
        }
    }
}

# Stop verified runtime Python processes before their launchers.
$OrderedTargets = $Targets | Sort-Object @{
    Expression = { if ($_.Name -in @("python.exe", "pythonw.exe")) { 0 } else { 1 } }
}
$StoppedPids = @()
foreach ($Process in $OrderedTargets) {
    $Current = Get-CimInstance Win32_Process -Filter "ProcessId = $($Process.ProcessId)" -ErrorAction SilentlyContinue
    if (
        !$Current -or
        $Current.CreationDate -ne $Process.CreationDate -or
        !(Test-VerifiedProcess -Process $Current -ProcessMap $ByPid)
    ) {
        Write-Warning "Process $($Process.ProcessId) changed or cannot be revalidated; skipped."
        continue
    }
    Stop-Process -Id $Process.ProcessId -Force -ErrorAction Stop
    $StoppedPids += [int]$Process.ProcessId
    Write-Host "Stopped verified $($Process.Name) PID $($Process.ProcessId)"
}

foreach ($PidName in @("searxng.pid", "broker.pid")) {
    $PidFile = Join-Path $RootFull $PidName
    if (!(Test-Path -LiteralPath $PidFile)) {
        continue
    }
    $RawPid = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    $RecordedPid = 0
    if (![int]::TryParse([string]$RawPid, [ref]$RecordedPid)) {
        Write-Warning "Invalid $PidName; keeping it for inspection."
        continue
    }
    if (
        $StoppedPids -contains $RecordedPid -or
        !(Get-Process -Id $RecordedPid -ErrorAction SilentlyContinue)
    ) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    } else {
        Write-Warning "$PidName refers to an unverified running process; left intact."
    }
}

if ($StoppedPids.Count) {
    Write-Host "Verified SearXNG and API Pool processes stopped."
} else {
    Write-Host "No verified SearXNG or API Pool processes were stopped."
}
