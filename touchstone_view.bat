@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM --- always run from this script's folder ---
cd /d "%~dp0"

set "APP=app.py"
set "REQ=requirements.txt"
set "VENV=.venv"

echo.
echo ==========================================
echo   Touchstone Viewer - Launcher
echo ==========================================
echo.

REM --- sanity checks ---
if not exist "%APP%" (
  echo ERROR: "%APP%" not found in:
  echo   %cd%
  echo Put run_touchstone_viewer.bat next to app.py
  pause
  exit /b 1
)

if not exist "%REQ%" (
  echo ERROR: "%REQ%" not found in:
  echo   %cd%
  echo Create requirements.txt (see instructions).
  pause
  exit /b 1
)

REM --- locate Python: prefer py launcher, then python ---
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if "%PY%"=="" (
  where python >nul 2>&1 && set "PY=python"
)

REM --- if no python, try winget install ---
if "%PY%"=="" (
  echo Python not found.
  echo Trying to install Python with winget (if available)...
  echo.

  where winget >nul 2>&1
  if errorlevel 1 (
    echo winget not found. Cannot auto-install Python.
    echo Please install Python 3.9+ from:
    echo   https://www.python.org/downloads/
    echo Then run this .bat again.
    pause
    exit /b 1
  )

  winget install -e --id Python.Python.3.11 --silent --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo winget install failed or was blocked by policy.
    echo Please install Python manually:
    echo   https://www.python.org/downloads/
    pause
    exit /b 1
  )

  echo.
  echo Python install command finished.
  echo NOTE: You may need to CLOSE this window and run the .bat again
  echo       (PATH/py launcher may not be visible until a new shell).
  echo.

  where py >nul 2>&1 && set "PY=py -3"
  if "%PY%"=="" (
    where python >nul 2>&1 && set "PY=python"
  )

  if "%PY%"=="" (
    echo Python still not detected in this shell.
    echo Close this window and double-click the .bat again.
    pause
    exit /b 0
  )
)

REM --- show python version ---
echo Using: %PY%
%PY% -c "import sys; print('Python:', sys.version.split()[0])"
if errorlevel 1 (
  echo ERROR: Python is not working correctly.
  pause
  exit /b 1
)

REM --- create venv if missing ---
if not exist "%VENV%\Scripts\python.exe" (
  echo.
  echo Creating virtual environment: %VENV%
  %PY% -m venv "%VENV%"
  if errorlevel 1 (
    echo ERROR: Failed to create venv. Your Python may be missing venv support.
    pause
    exit /b 1
  )
)

set "VPY=%cd%\%VENV%\Scripts\python.exe"
set "VPIP=%cd%\%VENV%\Scripts\pip.exe"

REM --- upgrade packaging tools ---
echo.
echo Upgrading pip/setuptools/wheel...
"%VPY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
  echo ERROR: pip upgrade failed (network/proxy restrictions?).
  pause
  exit /b 1
)

REM --- install requirements into venv ---
echo.
echo Installing requirements from %REQ% ...
"%VPIP%" install -r "%REQ%"
if errorlevel 1 (
  echo.
  echo ERROR: Dependency install failed.
  echo Common causes: corporate proxy, blocked PyPI, SSL inspection.
  echo If you're on a company network, you may need an internal PyPI mirror.
  pause
  exit /b 1
)

REM --- run streamlit app ---
echo.
echo Starting app...
echo If your browser does not open, visit: http://localhost:8501
echo (Close this window to stop the app.)
echo.

"%VPY%" -m streamlit run "%APP%" --browser.gatherUsageStats=false

echo.
echo App stopped.
pause
exit /b 0
