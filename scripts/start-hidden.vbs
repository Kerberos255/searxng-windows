Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell -ExecutionPolicy Bypass -File E:\openclaw\searxng_windows\scripts\start.ps1", 0
Set WshShell = Nothing
