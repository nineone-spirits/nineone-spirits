@echo off
REM Start TextGrabber without a console window.
REM Probes: project .venv, then parent .venv, then py -3 on PATH.
setlocal
cd /d "%~dp0"

call :try "%~dp0.venv\Scripts\pythonw.exe"
if not errorlevel 1 exit /b 0
call :try "%~dp0..\.venv\Scripts\pythonw.exe"
if not errorlevel 1 exit /b 0
call :trypy
if not errorlevel 1 exit /b 0

echo.
echo [x] No usable Python environment found.
echo     Run install.bat first (about 110 MB of dependencies), then run this file again.
echo     To see the actual error, open a terminal and run:
echo         .venv\Scripts\python.exe run.py
echo.
pause
exit /b 1

:try
if not exist "%~1" exit /b 1
"%~1" -c "import rapidocr, PIL, numpy" >nul 2>nul
if errorlevel 1 exit /b 1
start "" "%~1" "%~dp0run.py"
exit /b 0

:trypy
where py >nul 2>nul
if errorlevel 1 exit /b 1
py -3 -c "import rapidocr, PIL, numpy" >nul 2>nul
if errorlevel 1 exit /b 1
start "" py -3 "%~dp0run.py"
exit /b 0
