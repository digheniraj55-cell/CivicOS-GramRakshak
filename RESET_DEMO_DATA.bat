@echo off
setlocal
cd /d "%~dp0"
echo =====================================================
echo   CivicOS Demo Database Reset - DATA WILL BE REPLACED
echo =====================================================
echo Stop CivicOS before continuing.
echo A timestamped copy of the current database will be saved in backups\.
set /p CONFIRM=Type YES to restore the bundled demo seed: 
if /I not "%CONFIRM%"=="YES" (
  echo Reset cancelled.
  pause
  exit /b 0
)
if not exist "demo_seed\civicos_demo_seed.db" (
  echo Demo seed not found.
  pause
  exit /b 1
)
if not exist backups mkdir backups
for /f "tokens=1-4 delims=/ " %%a in ('date /t') do set D=%%d-%%b-%%c
for /f "tokens=1-2 delims=: " %%a in ('time /t') do set T=%%a-%%b
copy /y civicos.db "backups\civicos_before_reset_%D%_%T%.db" >nul
copy /y "demo_seed\civicos_demo_seed.db" civicos.db >nul
echo Demo database restored successfully.
pause
