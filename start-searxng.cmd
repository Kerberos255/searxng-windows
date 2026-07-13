@echo off
setlocal
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start.ps1" -Root "%ROOT%" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo SearXNG start failed. Check the log files in:
  echo %ROOT%
  pause
)
exit /b %EXIT_CODE%
