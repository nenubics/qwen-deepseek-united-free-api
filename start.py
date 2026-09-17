#!/usr/bin/env python3
"""
Universal Cross-Platform Auto-Start & System Service Manager.
Supports macOS (launchd), Linux (systemd), and Windows (Startup folder / Task Scheduler).

Usage:
  python start.py                     # Run server and open Dashboard in browser
  python start.py --no-browser        # Run server without opening browser
  python start.py --port 8080         # Run on custom port
  python start.py --autostart         # Install system boot autostart (macOS, Linux, Windows)
  python start.py --remove-autostart  # Remove system boot autostart
  python start.py --status            # Check service and server status
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

OS_NAME = platform.system().lower()  # "darwin", "linux", "windows"


def get_python_exec() -> str:
    """Returns the best python executable (prefers .venv if present)."""
    if OS_NAME == "windows":
        venv_py = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        venv_py = ROOT_DIR / ".venv" / "bin" / "python"

    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def get_port_from_env() -> int:
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("PORT="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return int(val)
        except Exception:
            pass
    return 8000


def ensure_environment() -> None:
    """Ensures .env exists and required dependencies are installed."""
    env_file = ROOT_DIR / ".env"
    example_file = ROOT_DIR / ".env.example"
    if not env_file.exists() and example_file.exists():
        print("⚙️ Initializing .env from .env.example...")
        shutil.copy(example_file, env_file)

    # Check dependencies
    py = get_python_exec()
    try:
        subprocess.check_call(
            [py, "-c", "import fastapi, uvicorn, playwright, cryptography"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        print("📥 Missing dependencies. Installing from requirements.txt...")
        subprocess.check_call([py, "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([py, "-m", "pip", "install", "-r", str(ROOT_DIR / "requirements.txt")])
        print("🌐 Installing Playwright Chromium browser...")
        try:
            subprocess.check_call([py, "-m", "playwright", "install", "chromium"])
        except Exception as e:
            print(f"⚠️ Warning installing playwright browser: {e}")


# =====================================================================
# SYSTEM AUTOSTART (BOOT SERVICE)
# =====================================================================

def install_autostart_macos(port: int) -> None:
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.unified.qwen.deepseek.api.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    py = get_python_exec()

    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.unified.qwen.deepseek.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>{py}</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>app.main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>{port}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{ROOT_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{LOGS_DIR}/service.log</string>
    <key>StandardErrorPath</key>
    <string>{LOGS_DIR}/service_err.log</string>
</dict>
</plist>
"""
    plist_path.write_text(content, encoding="utf-8")
    print(f"✓ Created launchd plist at: {plist_path}")

    # Load service
    try:
        subprocess.run(["launchctl", "unload", str(plist_path)], stderr=subprocess.DEVNULL)
        subprocess.check_call(["launchctl", "load", "-w", str(plist_path)])
        print("🎉 macOS LaunchAgent loaded successfully! Service will autostart on every boot/login.")
        print(f"   Logs: tail -f '{LOGS_DIR}/service.log'")
    except Exception as e:
        print(f"⚠️ Failed to run launchctl load: {e}")


def remove_autostart_macos() -> None:
    plist_path = Path.home() / "Library" / "LaunchAgents" / "com.unified.qwen.deepseek.api.plist"
    if plist_path.exists():
        try:
            subprocess.run(["launchctl", "unload", str(plist_path)], stderr=subprocess.DEVNULL)
        except Exception:
            pass
        plist_path.unlink(missing_ok=True)
        print("✓ macOS LaunchAgent removed successfully.")
    else:
        print("No macOS LaunchAgent found.")


def install_autostart_linux(port: int) -> None:
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)
    service_file = service_dir / "unified-ai-api.service"
    py = get_python_exec()

    content = f"""[Unit]
Description=Unified Qwen & DeepSeek Free API Service
After=network.target

[Service]
Type=simple
WorkingDirectory={ROOT_DIR}
ExecStart={py} -m uvicorn app.main:app --host 0.0.0.0 --port {port}
Restart=always
RestartSec=5
StandardOutput=append:{LOGS_DIR}/service.log
StandardError=append:{LOGS_DIR}/service_err.log

[Install]
WantedBy=default.target
"""
    service_file.write_text(content, encoding="utf-8")
    print(f"✓ Created systemd service at: {service_file}")

    try:
        subprocess.check_call(["systemctl", "--user", "daemon-reload"])
        subprocess.check_call(["systemctl", "--user", "enable", "--now", "unified-ai-api.service"])
        print("🎉 Linux systemd user service enabled and started! Will autostart on every boot.")
        print("   Status: systemctl --user status unified-ai-api.service")
    except Exception as e:
        print(f"⚠️ Failed to enable systemd service: {e}")


def remove_autostart_linux() -> None:
    service_file = Path.home() / ".config" / "systemd" / "user" / "unified-ai-api.service"
    if service_file.exists():
        try:
            subprocess.run(["systemctl", "--user", "stop", "unified-ai-api.service"], stderr=subprocess.DEVNULL)
            subprocess.run(["systemctl", "--user", "disable", "unified-ai-api.service"], stderr=subprocess.DEVNULL)
        except Exception:
            pass
        service_file.unlink(missing_ok=True)
        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"], stderr=subprocess.DEVNULL)
        except Exception:
            pass
        print("✓ Linux systemd user service removed.")
    else:
        print("No Linux systemd service found.")


def install_autostart_windows(port: int) -> None:
    appdata = os.getenv("APPDATA")
    if not appdata:
        print("❌ Cannot find APPDATA directory.")
        return

    startup_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    vbs_path = startup_dir / "unified-ai-api.vbs"
    py = get_python_exec()

    # VBScript runs the server in completely hidden background window on startup
    content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{ROOT_DIR}"
WshShell.Run """{py}"" -m uvicorn app.main:app --host 0.0.0.0 --port {port}", 0, False
'''
    vbs_path.write_text(content, encoding="utf-8")
    print(f"🎉 Windows Startup launcher created at: {vbs_path}")
    print("   The API server will now automatically start in the background whenever you log into Windows.")


def remove_autostart_windows() -> None:
    appdata = os.getenv("APPDATA")
    if appdata:
        vbs_path = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "unified-ai-api.vbs"
        if vbs_path.exists():
            vbs_path.unlink()
            print("✓ Windows Startup launcher removed.")
            return
    print("No Windows Startup launcher found.")


def handle_autostart(install: bool, port: int) -> None:
    if install:
        print(f"🔧 Configuring automatic system boot startup for {platform.system()}...")
        if OS_NAME == "darwin":
            install_autostart_macos(port)
        elif OS_NAME == "linux":
            install_autostart_linux(port)
        elif OS_NAME == "windows":
            install_autostart_windows(port)
        else:
            print(f"❌ Autostart not supported on OS: {platform.system()}")
    else:
        print(f"🧹 Removing autostart configuration for {platform.system()}...")
        if OS_NAME == "darwin":
            remove_autostart_macos()
        elif OS_NAME == "linux":
            remove_autostart_linux()
        elif OS_NAME == "windows":
            remove_autostart_windows()


# =====================================================================
# SERVER RUNNER
# =====================================================================

def run_server(port: int, open_browser: bool = True) -> None:
    ensure_environment()

    py = get_python_exec()
    url = f"http://localhost:{port}/dashboard"

    print("========================================================")
    print(f"  🚀 Unified Qwen & DeepSeek Free API Server")
    print(f"  🌐 URL:               http://localhost:{port}")
    print(f"  🖥️ Web Dashboard:     {url}")
    print(f"  🔑 Default API Key:   sk-unified-free-key")
    print(f"  ⚡ Running on Python:  {py}")
    print("========================================================")

    if open_browser:
        def _open():
            time.sleep(1.8)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        import threading
        threading.Thread(target=_open, daemon=True).start()

    cmd = [py, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(port)]
    try:
        subprocess.run(cmd, cwd=str(ROOT_DIR))
    except KeyboardInterrupt:
        print("\n👋 Server stopped.")


def main():
    parser = argparse.ArgumentParser(description="Unified Qwen & DeepSeek Free API Launcher")
    parser.add_argument("--port", type=int, default=None, help="Port to run the server on (default: from .env or 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser dashboard on start")
    parser.add_argument("--autostart", action="store_true", help="Install background autostart service on boot (macOS, Linux, Windows)")
    parser.add_argument("--remove-autostart", action="store_true", help="Uninstall background autostart service")
    parser.add_argument("--status", action="store_true", help="Check server and autostart service status")

    args = parser.parse_args()
    port = args.port or get_port_from_env()

    if args.autostart:
        handle_autostart(install=True, port=port)
        return

    if args.remove_autostart:
        handle_autostart(install=False, port=port)
        return

    if args.status:
        print("=== System Status ===")
        print(f"OS: {platform.system()} ({platform.release()})")
        print(f"Python: {get_python_exec()}")
        print(f"Port: {port}")
        if OS_NAME == "darwin":
            p = Path.home() / "Library" / "LaunchAgents" / "com.unified.qwen.deepseek.api.plist"
            print(f"macOS Autostart installed: {'YES (' + str(p) + ')' if p.exists() else 'NO'}")
        elif OS_NAME == "linux":
            s = Path.home() / ".config" / "systemd" / "user" / "unified-ai-api.service"
            print(f"Linux Autostart installed: {'YES (' + str(s) + ')' if s.exists() else 'NO'}")
        elif OS_NAME == "windows":
            appdata = os.getenv("APPDATA")
            v = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "unified-ai-api.vbs" if appdata else None
            print(f"Windows Autostart installed: {'YES' if v and v.exists() else 'NO'}")
        return

    run_server(port=port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
