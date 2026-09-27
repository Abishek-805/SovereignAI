@echo off
setlocal
cd /d "%~dp0"
title SovereignAI - Stop
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-sovereign.ps1"
if errorlevel 1 (
  echo.
  echo Shutdown needs attention. See the error above.
  pause
  exit /b 1
)
exit /b 0
