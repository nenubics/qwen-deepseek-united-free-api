#!/usr/bin/env python3
"""
CLI utility for managing authentication and accounts for Qwen and DeepSeek.

Usage:
    python login.py --status                # View accounts status for both providers
    python login.py --qwen                  # Interactive browser login for Qwen
    python login.py --qwen-token <TOKEN>    # Add Qwen Bearer token manually
    python login.py --deepseek              # Interactive browser login for DeepSeek
    python login.py --deepseek --profile p1 # Login for a specific DeepSeek profile
    python login.py --list-models           # List supported models and aliases
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Ensure app is importable
SYS_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SYS_ROOT))

from app.config import settings
from app.model_registry import (
    list_all_models,
    DEEPSEEK_TOGGLES,
    QWEN_CANONICAL_MODELS,
    QWEN_ALIASES,
)
from app.qwen import token_manager
from app.qwen.browser_auth import login_qwen_interactive


def cmd_status() -> int:
    print("=" * 60)
    print("           UNIFIED API ACCOUNTS STATUS")
    print("=" * 60)
    
    # 1. Qwen Status
    print("\n[Qwen Accounts]")
    tokens = token_manager.load_tokens()
    if not tokens:
        print("  No Qwen tokens found in session/tokens.json")
        print("  Run: python login.py --qwen  or  python login.py --qwen-token <TOKEN>")
    else:
        now = time.time()
        for i, acc in enumerate(tokens, 1):
            acc_id = acc.get("id", f"account_{i}")
            label = acc.get("label", "")
            raw_token = acc.get("token", "")
            payload = token_manager.decode_jwt_payload(raw_token) if raw_token else None
            exp = payload.get("exp", 0) if payload else 0
            is_invalid = acc.get("invalid", False)
            reset_at = acc.get("resetAt")
            
            if is_invalid:
                status_str = "INVALID"
            elif reset_at:
                status_str = f"RATE LIMITED (until {reset_at})"
            elif exp > 0:
                if exp > now:
                    rem_h = (exp - now) / 3600
                    status_str = f"ACTIVE (expires in {rem_h:.1f}h)"
                else:
                    status_str = "EXPIRED"
            else:
                status_str = "ACTIVE"

            masked_token = raw_token
            if len(masked_token) > 16:
                masked_token = masked_token[:6] + "..." + masked_token[-6:]

            print(f"  {i}. ID: {acc_id} | Label: {label or 'unlabeled'}")
            print(f"     Token: {masked_token} | Status: {status_str}")

    # 2. DeepSeek Status
    print("\n[DeepSeek Profiles]")
    from app.deepseek.session_pool import load_profiles
    profiles = load_profiles(settings.USER_DATA_DIR, settings.COOKIE_FILE)
    if not profiles:
        print("  No DeepSeek profiles configured.")
    else:
        for p in profiles:
            udd = Path(p.user_data_dir)
            if not udd.is_absolute():
                udd = SYS_ROOT / udd
            has_data = udd.exists() and any(udd.iterdir()) if udd.exists() else False
            status_desc = "READY (persistent session detected)" if has_data else "EMPTY / NEEDS LOGIN"
            print(f"  - Profile: {p.name}")
            print(f"    Directory: {udd}")
            print(f"    Status:    {status_desc}")

    # 3. Server Configuration
    print("\n[Unified Server Config]")
    print(f"  Host: {settings.HOST}:{settings.PORT}")
    print(f"  Unified API Key: {settings.API_KEY[:6]}...{settings.API_KEY[-4:] if len(settings.API_KEY) > 10 else ''}")
    print(f"  Default Model:   {settings.DEFAULT_MODEL}")
    print("=" * 60)
    return 0


def cmd_list_models() -> int:
    print("=" * 65)
    print("           REGISTERED MODELS & ROUTING")
    print("=" * 65)
    print("\n[DeepSeek Engine Models]")
    for m in DEEPSEEK_TOGGLES:
        print(f"  * {m:<25} -> DeepSeek Browser Pool")

    print("\n[Qwen Engine Models]")
    for m in QWEN_CANONICAL_MODELS:
        print(f"  * {m:<25} -> Qwen API Direct Stream")

    print("\n[Convenience Aliases]")
    for alias, target in QWEN_ALIASES.items():
        print(f"  * {alias:<25} -> maps to '{target}'")
    print("  * deepseek-reasoner         -> maps to 'deepseek-think'")
    print("  * deepseek-r1               -> maps to 'deepseek-think'")
    print("=" * 65)
    return 0


def cmd_qwen_token(token: str) -> int:
    token = token.strip()
    if not token:
        print("Error: empty token provided.")
        return 1
    acc = token_manager.add_or_update_token(token_str=token, label="cli_imported")
    print(f"Successfully saved Qwen token for account '{acc.get('id')}'.")
    print("Status:", "Valid" if token_manager.get_available_token() else "Failed/Expired")
    return 0


def cmd_qwen_interactive() -> int:
    print("\nStarting interactive login for Qwen...")
    print("A browser window will open. Please sign in to your Qwen account.")
    print("Once logged in, the token will be detected and saved automatically.\n")
    
    result = asyncio.run(login_qwen_interactive(headless=False))
    if result.get("success"):
        acc = result.get("account", {})
        print(f"\nSUCCESS: Qwen account '{acc.get('id', 'unknown')}' logged in and saved to session/tokens.json!")
        return 0
    else:
        print(f"\nFAILED: {result.get('error', 'Login was not completed')}")
        return 1


def cmd_deepseek_interactive(profile_name: str = "default") -> int:
    try:
        from patchright.async_api import async_playwright
    except ImportError:
        from playwright.async_api import async_playwright

    from app.deepseek.session_pool import load_profiles
    profiles = load_profiles(settings.USER_DATA_DIR, settings.COOKIE_FILE)
    target_prof = None
    for p in profiles:
        if p.name == profile_name:
            target_prof = p
            break
    if not target_prof:
        # Fallback to default user_data_dir
        udd_path = str(SYS_ROOT / settings.USER_DATA_DIR)
        target_prof_name = profile_name
    else:
        udd_path = target_prof.user_data_dir
        if not Path(udd_path).is_absolute():
            udd_path = str(SYS_ROOT / udd_path)
        target_prof_name = target_prof.name

    print(f"\nStarting interactive login for DeepSeek profile: '{target_prof_name}'")
    print(f"Data directory: {udd_path}")
    print("A browser window will open. Please log in to https://chat.deepseek.com.")
    print("The session will be saved to your profile data directory.\n")

    async def _run() -> int:
        pw = await async_playwright().start()
        try:
            ctx = await pw.chromium.launch_persistent_context(
                user_data_dir=udd_path,
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = await ctx.new_page()
            await page.goto(settings.CHAT_URL)
            
            timeout_s = settings.LOGIN_WAIT_TIMEOUT_MS // 1000
            start = time.time()
            print(f"Waiting up to {timeout_s}s for login confirmation...")
            
            while time.time() - start < timeout_s:
                try:
                    # Look for input textarea marking active chat session
                    if await page.query_selector("textarea"):
                        print("\nSUCCESS: Login marker detected (chat textarea present).")
                        print(f"Session state saved in {udd_path}!")
                        return 0
                except Exception:
                    pass
                await asyncio.sleep(2)
                
            print("\nTIMEOUT: Login was not completed within the time limit.")
            return 1
        finally:
            try:
                await ctx.close()
            except Exception:
                pass
            await pw.stop()

    return asyncio.run(_run())


def cmd_add_cookies(raw_cookies: str, provider: str = "auto", profile: str = "default") -> int:
    from app.cookie_importer import apply_cookies
    print(f"\nProcessing cookies (provider={provider})...")
    res = apply_cookies(raw_cookies, target_provider=provider, profile_name=profile)
    if not res.get("success"):
        print(f"FAILED: {res.get('error')}")
        return 1
    print(f"SUCCESS: Parsed {res.get('total_parsed_cookies')} cookies!")
    print(f"Detected provider: {res.get('detected_provider')}")
    for prov, det in res.get("details", {}).items():
        print(f"  * {prov}: {det.get('cookie_count')} cookies saved ({det.get('cookie_file') or det.get('account_id') or 'OK'})")
    return 0


def cmd_cookie_file(file_path: str, provider: str = "auto", profile: str = "default") -> int:
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File '{file_path}' does not exist.")
        return 1
    content = path.read_text(encoding="utf-8", errors="ignore")
    return cmd_add_cookies(content, provider=provider, profile=profile)


def cmd_auto_cookies() -> int:
    from app.cookie_importer import scan_local_cookie_files, auto_import_from_scanned_files
    print("\nScanning local folders (workspace, Downloads, Desktop) for cookie files...")
    files = scan_local_cookie_files()
    if not files:
        print("No cookie export files (.txt, .json) found.")
        print("Tip: Export cookies using an extension (like 'Get cookies.txt locally' or 'Cookie-Editor')")
        print("and drop the file into this folder or your Downloads directory.")
        return 0

    print(f"Found {len(files)} candidate file(s):")
    for f in files:
        print(f"  - {f['filename']} ({f['size_bytes']} bytes) -> Provider: {f['detected_provider']}, Cookies: {f['cookie_count']}")

    print("\nAutomatically importing matching cookies...")
    res = auto_import_from_scanned_files()
    if res.get("success"):
        print(f"SUCCESS: {res.get('message')}")
        for imp in res.get("files", []):
            print(f"  * Imported '{imp['file']}' for {imp['provider']}")
        return 0
    else:
        print(f"Notice: {res.get('message')}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified Qwen + DeepSeek API Authentication & Cookie CLI",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--status", action="store_true", help="Display status of all Qwen accounts and DeepSeek profiles")
    parser.add_argument("--list-models", action="store_true", help="List all available models, aliases, and providers")
    parser.add_argument("--qwen", "--qwen-login", action="store_true", help="Interactive browser login for Qwen")
    parser.add_argument("--qwen-token", type=str, metavar="TOKEN", help="Save a Qwen Bearer JWT token directly")
    parser.add_argument("--deepseek", "--deepseek-login", action="store_true", help="Interactive browser login for DeepSeek")
    parser.add_argument("--profile", type=str, default="default", help="DeepSeek profile name (default: 'default')")
    parser.add_argument("--add-cookies", type=str, metavar="COOKIES", help="Add raw cookies (HTTP header string, Netscape, or JSON)")
    parser.add_argument("--cookie-file", type=str, metavar="PATH", help="Import cookies from a cookies.txt or cookies.json file")
    parser.add_argument("--auto-cookies", action="store_true", help="Scan Downloads and workspace for cookie files and auto-import")
    parser.add_argument("--target", type=str, default="auto", choices=["auto", "deepseek", "qwen", "both"], help="Target provider for cookies (default: auto)")

    args = parser.parse_args()

    if args.status:
        return cmd_status()
    elif args.list_models:
        return cmd_list_models()
    elif args.auto_cookies:
        return cmd_auto_cookies()
    elif args.cookie_file:
        return cmd_cookie_file(args.cookie_file, provider=args.target, profile=args.profile)
    elif args.add_cookies:
        return cmd_add_cookies(args.add_cookies, provider=args.target, profile=args.profile)
    elif args.qwen_token:
        return cmd_qwen_token(args.qwen_token)
    elif args.qwen:
        return cmd_qwen_interactive()
    elif args.deepseek:
        return cmd_deepseek_interactive(args.profile)
    else:
        # Default action: show status
        return cmd_status()


if __name__ == "__main__":
    sys.exit(main())
