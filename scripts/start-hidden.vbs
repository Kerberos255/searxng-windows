Set WshShell = CreateObject("WScript.Shell")
Set FileSystem = CreateObject("Scripting.FileSystemObject")
ScriptDir = FileSystem.GetParentFolderName(WScript.ScriptFullName)
RootDir = FileSystem.GetParentFolderName(ScriptDir)
WshShell.Run "powershell -ExecutionPolicy Bypass -File """ & ScriptDir & "\start.ps1"" -Root """ & RootDir & """", 0
Set WshShell = Nothing
