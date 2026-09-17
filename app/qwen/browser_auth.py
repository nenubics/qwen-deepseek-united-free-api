"""
Interactive and Automated Playwright Login for Qwen Chat.
Extracts Bearer token & cookies and saves to session/tokens.json.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

from playwright.async_api import async_playwright

from app.config import settings
from app.qwen import token_manager

logger = logging.getLogger("qwen.auth")


async def login_qwen_interactive(
    email: Optional[str] = None,
    password: Optional[str] = None,
    headless: bool = False,
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """
    Launches browser for Qwen authentication, waits for sign-in,
    extracts token and cookies, and registers the account in tokens.json.
    """
    logger.info(f"Starting browser for Qwen authorization (headless={headless})...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        auth_url = f"{settings.QWEN_BASE_URL}/auth?action=signin"
        await page.goto(auth_url)

        if email and password:
            try:
                await page.wait_for_selector('input[type="text"], input[type="email"], #username', timeout=15000)
                await page.fill('input[type="text"], input[type="email"], #username', email)
                await page.keyboard.press("Enter")
                await asyncio.sleep(2)
                await page.wait_for_selector('input[type="password"], #password', timeout=10000)
                await page.fill('input[type="password"], #password', password)
                await page.keyboard.press("Enter")
            except Exception as e:
                logger.warning(f"Auto-fill for credentials did not complete: {e}. Please complete login in browser.")

        # Polling loop waiting for token in localStorage
        start_time = time.time()
        token = None
        while time.time() - start_time < timeout_seconds:
            try:
                token = await page.evaluate("localStorage.getItem('token')")
                if token and token.startswith("ey"):
                    break
            except Exception:
                pass
            await asyncio.sleep(2)

        if not token:
            await browser.close()
            return {"success": False, "error": "Login timeout or token not found."}

        # Extract user information for account name
        account_name = email or ""
        try:
            user_info_raw = await page.evaluate("localStorage.getItem('user_info')")
            if user_info_raw:
                uinfo = json.loads(user_info_raw)
                account_name = uinfo.get("email") or uinfo.get("nickname") or account_name
        except Exception:
            pass

        if not account_name:
            account_name = f"qwen_{int(time.time() * 1000)}"

        cookies = await context.cookies()
        await browser.close()

        acc = token_manager.add_or_update_token(
            token_str=token,
            account_id=account_name,
            label=account_name,
            cookies=cookies,
        )

        logger.info(f"Qwen account '{account_name}' successfully authorized and saved!")
        return {"success": True, "account": acc}
