@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\kabuki-cord-desktop.exe" (
  echo Kabuki-Cord is not installed yet. Starting installer...
  call "%~dp0Install-Kabuki-Cord.cmd" -NoLaunch
  if errorlevel 1 exit /b 1
)

start "Kabuki-Cord" "%~dp0.venv\Scripts\kabuki-cord-desktop.exe"
exit /b 0
