@echo off
setlocal
cd /d "%~dp0"
echo.
echo ===============================================
echo            CivicOS Local Launcher
echo ===============================================
echo.
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher ^(py^) was not found. Install Python 3.11+ and try again.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating virtual environment...
  py -m venv .venv
)
call ".venv\Scripts\activate.bat"
echo [2/3] Installing/updating required packages...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Package installation failed. Check your internet connection and Python installation.
  pause
  exit /b 1
)
echo [3/3] Starting CivicOS...
echo CivicOS will open on http://127.0.0.1:5000/ so browser live-location permission works on this laptop.
echo Press Ctrl+C in this window to stop the server.
echo.
start "" cmd /c "timeout /t 2 /nobreak >nul & start "" http://127.0.0.1:5000/"
python app.py
pause
