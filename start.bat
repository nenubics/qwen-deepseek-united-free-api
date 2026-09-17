@echo off
REM ==============================================================================
REM Unified Qwen & DeepSeek Free API - 1-Click Auto-Starter for Windows
REM ==============================================================================

chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   🚀 Starting Unified Qwen & DeepSeek Free API Server
echo ========================================================

REM 1. Check Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] Python is not installed or not in PATH.
        echo Please install Python 3.10+ from https://www.python.org/downloads/
        echo (Make sure to check "Add Python to PATH" during installation)
        pause
        exit /b 1
    ) else (
        set "PY_CMD=py -3"
    )
) else (
    set "PY_CMD=python"
)

REM 2. Create virtual environment if missing
if not exist ".venv" (
    echo [*] Creating virtual environment (.venv)...
    %PY_CMD% -m venv .venv
)

call .venv\Scripts\activate.bat

REM 3. Create .env if missing
if not exist ".env" (
    if exist ".env.example" (
        echo [*] Creating .env from .env.example...
        copy .env.example .env >nul
    )
)

REM 4. Check dependencies
python -c "import fastapi, uvicorn, playwright, cryptography" >nul 2>nul
if %errorlevel% neq 0 (
    echo [*] Installing dependencies from requirements.txt...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    echo [*] Installing Playwright Chromium browser...
    playwright install chromium
)

set PORT=8000
for /f "tokens=2 delims==" %%I in ('findstr /b "PORT=" .env 2^>nul') do set PORT=%%I
set "PORT=%PORT: =%"
if "%PORT%"=="" set PORT=8000

echo ========================================================
echo   🎉 Server running at: http://localhost:%PORT%
echo   🖥️ Opening Dashboard: http://localhost:%PORT%/dashboard
echo   🔑 Default API Key:   sk-unified-free-key
echo   Press Ctrl+C to stop the server.
echo ========================================================

start "" "http://localhost:%PORT%/dashboard"

uvicorn app.main:app --host 0.0.0.0 --port %PORT%
pause
