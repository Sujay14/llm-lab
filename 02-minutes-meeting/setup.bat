@echo off
REM One-time setup for Meeting Minutes Creator (Windows)
cd /d "%~dp0"

echo [1/3] Creating virtual environment...
python -m venv venv || (echo Python was not found. Install Python 3.10+ first. & pause & exit /b 1)

echo [2/3] Installing packages...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || (echo Package install failed. & pause & exit /b 1)

echo [3/3] Pulling the Llama 3.2 model (skips if already present)...
ollama pull llama3.2

echo.
echo Setup complete. Double-click run.bat to start the app.
pause
