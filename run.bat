@echo off
REM 启动屏幕取字（无控制台窗口）
REM 依次探测：项目内 .venv -> 上级 .venv -> PATH 上的 py -3
setlocal
cd /d "%~dp0"

call :try "%~dp0.venv\Scripts\pythonw.exe"
if not errorlevel 1 exit /b 0
call :try "%~dp0..\.venv\Scripts\pythonw.exe"
if not errorlevel 1 exit /b 0
call :trypy
if not errorlevel 1 exit /b 0

echo.
echo [x] 没有找到装好依赖的 Python 环境。
echo     请先双击 install.bat 安装依赖（约 110 MB），再双击本文件。
echo     想看具体报错，请在命令行执行：
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
