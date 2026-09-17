#!/usr/bin/env bash
# ==============================================================================
# Unified Qwen & DeepSeek Free API - 1-Click Auto-Starter for macOS & Linux
# ==============================================================================

set -e

# Change to the directory of this script
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "========================================================"
echo "  🚀 Starting Unified Qwen & DeepSeek Free API Server   "
echo "========================================================"

# 1. Check Python
PYTHON_BIN=""
if command -v python3 &>/dev/null; then
    PYTHON_BIN="python3"
elif command -v python &>/dev/null; then
    PYTHON_BIN="python"
else
    echo "❌ Python is not installed. Please install Python 3.10+ (https://www.python.org/downloads/)"
    exit 1
fi

echo "✓ Using Python: $($PYTHON_BIN --version)"

# 2. Check or create virtual environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment (.venv)..."
    $PYTHON_BIN -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# 3. Check / copy .env
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "⚙️ Creating .env from .env.example..."
        cp .env.example .env
    fi
fi

# 4. Install dependencies if not already installed
if ! python -c "import fastapi, uvicorn, playwright, cryptography" &>/dev/null; then
    echo "📥 Installing dependencies from requirements.txt..."
    pip install --upgrade pip
    pip install -r requirements.txt
    echo "🌐 Installing Playwright Chromium browser..."
    playwright install chromium
fi

# 5. Extract PORT from .env or default to 8000
PORT=$(grep -E "^PORT=" .env 2>/dev/null | cut -d '=' -f2 | tr -d ' "[:space:]' || echo "8000")
if [ -z "$PORT" ]; then
    PORT=8000
fi

URL="http://localhost:${PORT}/dashboard"

# 6. Open dashboard in browser in background after short delay
(
    sleep 1.8
    if command -v open &>/dev/null; then
        # macOS
        open "$URL" &>/dev/null || true
    elif command -v xdg-open &>/dev/null; then
        # Linux
        xdg-open "$URL" &>/dev/null || true
    fi
) &

echo "========================================================"
echo "  🎉 Server running at: http://localhost:${PORT}"
echo "  🖥️ Opening Dashboard: ${URL}"
echo "  🔑 Default API Key:   sk-unified-free-key"
echo "  Press Ctrl+C to stop the server."
echo "========================================================"

# 7. Start Uvicorn Server
exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
