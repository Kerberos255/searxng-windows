@echo off
setlocal
rem Keep the trailing slash away from the closing quote of -Root.
set "ROOT=%~dp0."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\stop.ps1" -Root "%ROOT%"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" if not defined CI pause
exit /b %EXIT_CODE%
