"""
DeepSeek Browser Automation Provider.
"""

from app.deepseek.browser_session import (
    BrowserSession,
    BrowserSessionError,
    browser_session,
)
from app.deepseek.session_pool import (
    SessionPool,
    PoolExhaustedError,
    load_profiles,
)
from app.deepseek.crypto_store import session_store
from app.deepseek.search_client import search_web
from app.deepseek.summarizer import summarize_text, SummarizerUnavailableError

__all__ = [
    "BrowserSession",
    "BrowserSessionError",
    "browser_session",
    "SessionPool",
    "PoolExhaustedError",
    "load_profiles",
    "session_store",
    "search_web",
    "summarize_text",
    "SummarizerUnavailableError",
]
