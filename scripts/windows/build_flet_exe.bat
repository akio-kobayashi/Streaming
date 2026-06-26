@echo off
setlocal

pushd "%~dp0\..\.." >nul
if errorlevel 1 (
    echo Failed to enter project directory: %~dp0\..\..
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

python -m pip install --upgrade pip
python -m pip install -r requirements-flet.txt
python -m pip install pyinstaller

python scripts\windows\create_icon.py assets\app-icon.ico
if errorlevel 1 (
    echo Failed to generate icon.
    popd >nul
    pause
    exit /b 1
)

pyinstaller ^
  --name StreamingASRClient ^
  --noconfirm ^
  --windowed ^
  --icon assets\app-icon.ico ^
  --collect-all flet ^
  --collect-all websockets ^
  client\flet\app.py

if errorlevel 1 (
    echo Build failed.
    popd >nul
    pause
    exit /b 1
)

echo Built dist\StreamingASRClient\StreamingASRClient.exe
pause
popd >nul
endlocal
