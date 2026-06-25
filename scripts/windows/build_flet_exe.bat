@echo off
setlocal

cd /d "%~dp0\..\.."

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

python -m pip install --upgrade pip
python -m pip install -r requirements-flet.txt
python -m pip install pyinstaller

python scripts\windows\create_icon.py assets\app-icon.ico
if errorlevel 1 (
    echo Failed to generate icon.
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
    pause
    exit /b 1
)

echo Built dist\StreamingASRClient\StreamingASRClient.exe
pause
endlocal
