@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-campus-repair.ps1"
if errorlevel 1 pause
endlocal
