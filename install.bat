@echo off
REM 一键安装：创建虚拟环境 -> 装依赖 -> 注册 textgrabber 命令
REM 只接受带 tkinter 的 Python：界面依赖 Tk，缺了会在启动时直接报错
REM 换镜像：set TEXTGRABBER_PIP_INDEX=https://pypi.org/simple 后再运行
REM 不走镜像：set TEXTGRABBER_NO_MIRROR=1 后再运行
setlocal
cd /d "%~dp0"

set "PYEXE="
REM 1) py 启动器  2) PATH 上所有 python/Python3（逐个试，PATH 上第一个未必带 tkinter）
REM 3) 常见安装位置（官方安装器 / Anaconda / Miniconda）
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
  echo [x] 没有找到带 tkinter 的 Python 3.10+。
  echo     请到 https://www.python.org/downloads/windows/ 安装，
  echo     安装时勾选 Add python.exe to PATH，然后重新运行本脚本。
  echo.
  pause
  exit /b 1
)
echo [0/4] 使用的解释器：%PYEXE%

if not exist ".venv" (
  echo [1/4] 创建虚拟环境 .venv ...
  %PYEXE% -m venv .venv
  if errorlevel 1 (echo [x] 创建虚拟环境失败 & pause & exit /b 1)
) else (
  echo [1/4] 已存在 .venv，跳过创建
)

set "PIP=.venv\Scripts\python.exe -m pip"
set "INDEX_ARGS=-i https://pypi.tuna.tsinghua.edu.cn/simple"
if defined TEXTGRABBER_PIP_INDEX set "INDEX_ARGS=-i %TEXTGRABBER_PIP_INDEX%"
if /i "%TEXTGRABBER_NO_MIRROR%"=="1" set "INDEX_ARGS="

echo [2/4] 升级 pip / setuptools / wheel ...
%PIP% install --upgrade pip setuptools wheel %INDEX_ARGS%
if errorlevel 1 (
  echo [i] 镜像源不可用，改用官方 PyPI 重试 ...
  %PIP% install --upgrade pip setuptools wheel
)

echo [3/4] 安装运行时依赖（约 110 MB，首次较慢）...
%PIP% install -r requirements.txt %INDEX_ARGS%
if errorlevel 1 (
  echo [i] 镜像源不可用，改用官方 PyPI 重试 ...
  %PIP% install -r requirements.txt
)
if errorlevel 1 (
  echo [x] 依赖安装失败。请检查网络后重试，或把报错发到 Issues。
  pause
  exit /b 1
)

echo [4/4] 注册命令入口并校验 ...
%PIP% install -e . --no-build-isolation --no-deps %INDEX_ARGS% >nul 2>nul
if errorlevel 1 echo [i] 跳过命令入口注册（不影响使用 run.bat 启动）
.venv\Scripts\python.exe -c "import rapidocr, onnxruntime, PIL, numpy, tkinter"
if errorlevel 1 (echo [x] 依赖校验失败，请把上面的报错发到 Issues & pause & exit /b 1)

echo.
echo 安装完成。
echo   启动：双击 run.bat，或执行 .venv\Scripts\pythonw.exe run.py
echo   看报错：.venv\Scripts\python.exe run.py
echo   命令行：.venv\Scripts\textgrabber.exe
echo.
pause
exit /b 0

:probe
REM %1 = 解释器（可能是 py），%2 = 附加参数（如 -3）；一起探测，避免 py 取到错误的默认版本
if defined PYEXE exit /b 0
"%~1" %~2 -c "import tkinter, venv" >nul 2>nul
if errorlevel 1 exit /b 0
set "PYEXE="%~1" %~2"
exit /b 0
