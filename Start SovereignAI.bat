@echo off
setlocal
cd /d "%~dp0"
title SovereignAI - Start
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-sovereign.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. See the error above and README.md.
  pause
  exit /b 1
)
exit /b 0
