@echo off
setlocal
rem Keep the trailing slash away from the closing quote of -Root.
set "ROOT=%~dp0."
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\start.ps1" -Root "%ROOT%" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo SearXNG start failed. Read the error above.
  echo Logs may not exist if startup failed before a child process was created.
  echo Installation: %ROOT%
  if not defined CI pause
)
exit /b %EXIT_CODE%
