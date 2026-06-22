@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\windows\Install-Kabuki-Cord.ps1" %*
if errorlevel 1 (
  echo.
  echo Kabuki-Cord install failed. Review .state\install.log for details.
  pause
  exit /b 1
)

exit /b 0
