@echo off
setlocal

pushd "%~dp0" >nul
if errorlevel 1 (
    echo Failed to enter project directory: %~dp0
    pause
    exit /b 1
)

set "PYTHON_CMD="
python -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=python"

if "%PYTHON_CMD%"=="" (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if "%PYTHON_CMD%"=="" (
    echo Python 3 was not found.
    echo Install Python 3 from https://www.python.org/downloads/windows/
    echo Enable "Add python.exe to PATH", or install the Python Launcher.
    echo If the Microsoft Store python alias appears, disable it from Windows Settings.
    popd >nul
    pause
    exit /b 1
)

if not exist ".venv-flet\Scripts\python.exe" (
    echo Creating Python virtual environment...
    %PYTHON_CMD% -m venv .venv-flet
    if errorlevel 1 (
        echo Failed to create virtual environment.
        popd >nul
        pause
        exit /b 1
    )
)

call ".venv-flet\Scripts\activate.bat"

python -c "import flet, websockets" >nul 2>nul
if errorlevel 1 (
    echo Installing Flet client dependencies...
    python -m pip install --upgrade pip
    python -m pip install -r requirements-flet.txt
    if errorlevel 1 (
        echo Failed to install dependencies.
        popd >nul
        pause
        exit /b 1
    )
)

echo Starting Streaming ASR desktop client...
python -m client.flet.app %*
if errorlevel 1 (
    echo Client exited with an error.
    popd >nul
    pause
    exit /b 1
)

popd >nul
endlocal
