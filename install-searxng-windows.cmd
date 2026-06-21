@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-searxng-windows.ps1" %*
echo.
echo Installation finished or failed. Press any key to close.
pause >nul
