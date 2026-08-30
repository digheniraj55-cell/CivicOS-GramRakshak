@echo off
setlocal
cd /d "%~dp0"
echo ===============================================
echo        CivicOS Pre-Hackathon Health Check
echo ===============================================
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" tools\preflight.py
) else (
  py tools\preflight.py
)
echo.
pause
