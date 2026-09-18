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

REM 2. Check virtual environment or system packages
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    set "ACTUAL_PY=python"
) else (
    %PY_CMD% -c "import fastapi, uvicorn, playwright, cryptography" >nul 2>nul
    if %errorlevel% equ 0 (
        set "ACTUAL_PY=%PY_CMD%"
    ) else (
        echo [*] Creating virtual environment (.venv)...
        %PY_CMD% -m venv .venv
        call .venv\Scripts\activate.bat
        set "ACTUAL_PY=python"
    )
)

REM 3. Create .env if missing
if not exist ".env" (
    if exist ".env.example" (
        echo [*] Creating .env from .env.example...
        copy .env.example .env >nul
    )
)

REM 4. Check dependencies
%ACTUAL_PY% -c "import fastapi, uvicorn, playwright, cryptography" >nul 2>nul
if %errorlevel% neq 0 (
    echo [*] Installing dependencies from requirements.txt...
    %ACTUAL_PY% -m pip install --upgrade pip
    %ACTUAL_PY% -m pip install -r requirements.txt
    echo [*] Installing Playwright Chromium browser...
    %ACTUAL_PY% -m playwright install chromium
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

%ACTUAL_PY% -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
pause
