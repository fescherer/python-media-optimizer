@echo off
rem Builds dist\ImageVideoOptimizer.exe. Run it from a terminal in the project folder: build.bat
setlocal
cd /d "%~dp0"

rem 1. Create the virtual environment (only the first time)
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv || goto :error
)
set "PY=.venv\Scripts\python.exe"

rem 2. Install the pinned app requirements + PyInstaller
"%PY%" -m pip install --upgrade pip || goto :error
"%PY%" -m pip install -r requirements.txt pyinstaller==6.22.3 pyinstaller-hooks-contrib==2026.8 || goto :error

rem Placeholder icon if there is none yet
if not exist "assets\icon.ico" (
    "%PY%" assets\make_icon.py || goto :error
)

rem 3. Build from the spec (clean build every time)
"%PY%" -m PyInstaller --noconfirm --clean build.spec || goto :error

rem 4. Result
echo.
echo Build finished: %CD%\dist\ImageVideoOptimizer.exe
exit /b 0

:error
echo.
echo BUILD FAILED - see the messages above.
exit /b 1
