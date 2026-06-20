param(
    [string]$Root = "$env:USERPROFILE\Apps\searxng-windows",
    [string]$TaskName = "OpenClaw SearXNG"
)

$ErrorActionPreference = "Stop"

$Vbs = Join-Path $Root "scripts\start-hidden.vbs"
if (!(Test-Path $Vbs)) {
    Write-Host "start-hidden.vbs not found: $Vbs"
    exit 1
}

$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument ('"' + $Vbs + '"')
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 0)
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Start local SearXNG for OpenClaw at user logon." -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName,State,TaskPath
