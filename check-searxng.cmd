@echo off
setlocal
rem Keep the trailing slash away from the closing quote of -Root.
set "ROOT=%~dp0."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\check.ps1" -Root "%ROOT%"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not defined CI pause
exit /b %EXIT_CODE%
