@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv-flet\Scripts\python.exe" (
    echo Creating Python virtual environment...
    py -3 -m venv .venv-flet
    if errorlevel 1 (
        echo Failed to create virtual environment. Install Python 3 and enable the py launcher.
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
        pause
        exit /b 1
    )
)

echo Starting Streaming ASR desktop client...
python -m client.flet.app %*
if errorlevel 1 (
    echo Client exited with an error.
    pause
    exit /b 1
)

endlocal
