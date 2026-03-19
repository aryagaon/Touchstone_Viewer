@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "APP=app.py"
set "LOG=launcher_log.txt"

echo ========================================== > "%LOG%"
echo Touchstone Viewer Launcher (system python) >> "%LOG%"
echo Folder: %cd% >> "%LOG%"
echo ========================================== >> "%LOG%"
echo. >> "%LOG%"

if not exist "%APP%" (
  echo ERROR: app.py not found: %cd%\%APP% >> "%LOG%"
  echo ERROR: app.py not found in this folder.
  echo See: %LOG%
  pause
  exit /b 1
)

REM Pick python command
set "PY=python"
where py >nul 2>&1
if %errorlevel%==0 set "PY=py -3"

echo Using python command: %PY% >> "%LOG%"
%PY% -c "import sys; print('Python exe:', sys.executable); print('Python ver:', sys.version)" >> "%LOG%" 2>&1

REM Verify streamlit import BEFORE running (this is the #1 cause of instant exit)
%PY% -c "import streamlit; print('Streamlit:', streamlit.__version__)" >> "%LOG%" 2>&1
if %errorlevel% neq 0 (
  echo. >> "%LOG%"
  echo ERROR: streamlit is not installed for this Python. >> "%LOG%"
  echo.
  echo ERROR: Streamlit is not installed for your system Python.
  echo Open launcher_log.txt and install it with:
  echo   %PY% -m pip install streamlit
  echo.
  echo See: %LOG%
  pause
  exit /b 1
)

echo. >> "%LOG%"
echo Starting Streamlit... >> "%LOG%"
echo.
echo Starting Streamlit...
echo If it doesn't open automatically, go to:
echo   http://localhost:8501
echo.

REM Start browser, then start streamlit (streamlit keeps running until you stop it)


%PY% -m streamlit run "%APP%" --browser.gatherUsageStats=false >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo Streamlit exited with errorlevel %errorlevel% >> "%LOG%"

echo.
echo Streamlit exited. See: %LOG%
pause
exit /b 0
