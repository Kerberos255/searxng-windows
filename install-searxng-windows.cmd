@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-searxng-windows.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
  echo Installation failed. Read the error above.
) else (
  echo Installation completed.
)
if not defined CI (
  echo Press any key to close.
  pause >nul
)
exit /b %EXIT_CODE%
