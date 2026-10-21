@echo off
REM One-click setup: create .venv, install dependencies, register the textgrabber command.
REM Requires Python 3.10+ with tkinter (the GUI is built on Tk).
REM Custom index : set TEXTGRABBER_PIP_INDEX=https://pypi.org/simple
REM Skip mirror   : set TEXTGRABBER_NO_MIRROR=1
setlocal
cd /d "%~dp0"

set "PYEXE="
REM 1) py launcher  2) every python / python3 on PATH  3) common install locations
REM PATH lookup matters: the first "python" on PATH may be a stripped build without tkinter.
call :probe py -3
for /f "delims=" %%P in ('where python 2^>nul') do call :probe "%%~P"
for /f "delims=" %%P in ('where python3 2^>nul') do call :probe "%%~P"
call :probe "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
call :probe "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
call :probe "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
call :probe "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
call :probe "%ProgramFiles%\Python313\python.exe"
call :probe "%ProgramFiles%\Python312\python.exe"
call :probe "%USERPROFILE%\anaconda3\python.exe"
call :probe "%USERPROFILE%\miniconda3\python.exe"
call :probe "%ProgramData%\anaconda3\python.exe"
call :probe "%ProgramData%\miniconda3\python.exe"

if not defined PYEXE (
  echo [x] No Python 3.10+ with tkinter found.
  echo     Install it from https://www.python.org/downloads/windows/
  echo     and tick "Add python.exe to PATH", then run this file again.
  echo.
  pause
  exit /b 1
)
echo [0/4] Interpreter: %PYEXE%

if not exist ".venv" (
  echo [1/4] Creating virtual environment .venv ...
  %PYEXE% -m venv .venv
  if errorlevel 1 (echo [x] Failed to create the virtual environment. & pause & exit /b 1)
) else (
  echo [1/4] .venv already exists, skipping creation
)

set "PIP=.venv\Scripts\python.exe -m pip"
set "INDEX_ARGS=-i https://pypi.tuna.tsinghua.edu.cn/simple"
if defined TEXTGRABBER_PIP_INDEX set "INDEX_ARGS=-i %TEXTGRABBER_PIP_INDEX%"
if /i "%TEXTGRABBER_NO_MIRROR%"=="1" set "INDEX_ARGS="

echo [2/4] Upgrading pip / setuptools / wheel ...
%PIP% install --upgrade pip setuptools wheel %INDEX_ARGS%
if errorlevel 1 (
  echo [i] Mirror unavailable, retrying with the official PyPI ...
  %PIP% install --upgrade pip setuptools wheel
)

echo [3/4] Installing runtime dependencies (about 110 MB on first run) ...
%PIP% install -r requirements.txt %INDEX_ARGS%
if errorlevel 1 (
  echo [i] Mirror unavailable, retrying with the official PyPI ...
  %PIP% install -r requirements.txt
)
if errorlevel 1 (
  echo [x] Dependency installation failed. Check your network and try again.
  pause
  exit /b 1
)

echo [4/4] Registering the command entry point and verifying imports ...
%PIP% install -e . --no-build-isolation --no-deps %INDEX_ARGS% >nul 2>nul
if errorlevel 1 echo [i] Skipped the CLI entry point (run.bat still works)
.venv\Scripts\python.exe -c "import rapidocr, onnxruntime, PIL, numpy, tkinter"
if errorlevel 1 (echo [x] Dependency check failed, please report the error above. & pause & exit /b 1)

echo.
echo Setup complete.
echo   Start  : run.bat, or .venv\Scripts\pythonw.exe run.py
echo   Debug  : .venv\Scripts\python.exe run.py   (keeps the console open)
echo   CLI    : .venv\Scripts\textgrabber.exe
echo.
pause
exit /b 0

:probe
REM %1 = interpreter (may be "py"), %2 = extra argument such as -3
if defined PYEXE exit /b 0
"%~1" %~2 -c "import tkinter, venv" >nul 2>nul
if errorlevel 1 exit /b 0
set "PYEXE="%~1" %~2"
exit /b 0
