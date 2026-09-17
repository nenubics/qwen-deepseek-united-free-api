"""
Unified Configuration for Qwen & DeepSeek Free API Service.
"""

import json
import os
import random
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import load_dotenv, set_key

SYS_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = SYS_ROOT / os.getenv("ENV_FILE", ".env")
if not ENV_PATH.exists():
    ENV_PATH.touch()

load_dotenv(dotenv_path=ENV_PATH)


def _get_or_create_fernet_key() -> str:
    key = os.getenv("FERNET_KEY")
    if not key:
        key = Fernet.generate_key().decode()
        try:
            set_key(str(ENV_PATH), "FERNET_KEY", key)
        except Exception:
            pass
        os.environ["FERNET_KEY"] = key
    return key


def _jitter(base: float, spread_ratio: float = 0.15) -> float:
    delta = base * spread_ratio
    return base + random.uniform(-delta, delta)


class Settings:
    # ----------------- Server & Common -----------------
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    API_KEY: str = os.getenv("API_KEY", "sk-unified-free-key")
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "qwen3.7-max")
    ALLOWED_ORIGINS: list = [
        s.strip() for s in os.getenv("ALLOWED_ORIGINS", "*").split(",") if s.strip()
    ]
    DISABLE_RATE_LIMIT: bool = os.getenv("DISABLE_RATE_LIMIT", "false").lower() == "true"
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))

    # ----------------- DeepSeek Engine -----------------
    CHAT_URL: str = os.getenv("CHAT_URL", "https://chat.deepseek.com")
    HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
    BROWSER_CHANNEL: str = os.getenv("BROWSER_CHANNEL", "")
    USER_AGENT: str = os.getenv("USER_AGENT", "")
    ANTIDETECT: str = os.getenv("ANTIDETECT", "")
    USER_DATA_DIR: str = str(SYS_ROOT / os.getenv("USER_DATA_DIR", "./data/pw_profile"))
    COOKIE_FILE: str = str(SYS_ROOT / os.getenv("COOKIE_FILE", "./data/cookies.txt"))
    DATA_DIR: str = str(SYS_ROOT / os.getenv("DATA_DIR", "./data"))
    DB_PATH: str = str(SYS_ROOT / os.getenv("DB_PATH", "./data/sessions.sqlite3"))
    PROFILES_FILE: str = str(SYS_ROOT / os.getenv("PROFILES_FILE", "./profiles.json"))
    FERNET_KEY: str = _get_or_create_fernet_key()

    POOL_COOLDOWN_SECONDS: float = float(os.getenv("POOL_COOLDOWN_SECONDS", "300"))
    POOL_MAX_WAIT_SECONDS: float = float(os.getenv("POOL_MAX_WAIT_SECONDS", "120"))
    REQUEST_QUEUE_TIMEOUT: float = float(os.getenv("REQUEST_QUEUE_TIMEOUT", "5.0"))
    TABS_PER_PROFILE: int = max(1, int(os.getenv("TABS_PER_PROFILE", "1")))
    MEMORY_MODE: str = os.getenv("MEMORY_MODE", "client").strip().lower()
    MAX_MESSAGE_LENGTH: int = int(os.getenv("MAX_MESSAGE_LENGTH", "0"))
    MAX_FILES_PER_MESSAGE: int = int(os.getenv("MAX_FILES_PER_MESSAGE", "5"))
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "2"))
    WORK_DIR: str = os.getenv("WORK_DIR", str(SYS_ROOT))

    # DeepSeek Timeouts (ms)
    LOGIN_WAIT_TIMEOUT_MS: int = int(os.getenv("LOGIN_WAIT_TIMEOUT_MS", "300000"))
    NAV_TIMEOUT_MS: int = int(os.getenv("NAV_TIMEOUT_MS", "35000"))
    RESPONSE_TIMEOUT_MS: int = int(os.getenv("RESPONSE_TIMEOUT_MS", "360000"))
    ACTION_TIMEOUT_MS: int = int(os.getenv("ACTION_TIMEOUT_MS", "15000"))

    # DeepSeek Selectors
    SEL_MESSAGE_INPUT: str = os.getenv("SEL_MESSAGE_INPUT", "textarea")
    SEL_SEND_BUTTON: str = os.getenv(
        "SEL_SEND_BUTTON", "div.ds-button--primary.ds-button--filled.ds-button--circle"
    )
    SEL_ATTACH_BUTTON: str = os.getenv("SEL_ATTACH_BUTTON", "input[type='file']")
    SEL_FILE_INPUT: str = os.getenv("SEL_FILE_INPUT", "input[type='file']")
    SEL_ASSISTANT_BLOCK: str = os.getenv(
        "SEL_ASSISTANT_BLOCK", "[class*='assistant-message-main-content']"
    )
    SEL_LAST_RESPONSE: str = os.getenv(
        "SEL_LAST_RESPONSE", "[class*='assistant-message-main-content']:last-of-type"
    )
    SEL_LOADING_INDICATOR: str = os.getenv(
        "SEL_LOADING_INDICATOR", "div[class*='loading'], div[class*='stop']"
    )
    SEL_CHALLENGE_OVERLAY: str = os.getenv("SEL_CHALLENGE_OVERLAY", "#cf-overlay")
    CHALLENGE_TEXT: str = os.getenv("CHALLENGE_TEXT", "One more step before you proceed")
    SEL_DEEP_THINK_BUTTON: str = os.getenv("SEL_DEEP_THINK_BUTTON", "")
    SEL_SEARCH_BUTTON: str = os.getenv("SEL_SEARCH_BUTTON", "")
    DEEP_THINK_LABELS: list = [
        s.strip() for s in os.getenv(
            "DEEP_THINK_LABELS", "DeepThink,Deep Think,Глубокое мышление,Глубокое размышление"
        ).split(",") if s.strip()
    ]
    SEARCH_LABELS: list = [
        s.strip() for s in os.getenv(
            "SEARCH_LABELS", "Умный поиск,Search,Поиск,Веб-поиск"
        ).split(",") if s.strip()
    ]
    SEL_LOGGED_IN_MARKER: str = os.getenv("SEL_LOGGED_IN_MARKER", "textarea")
    SEL_NEW_CHAT_BUTTON: str = os.getenv("SEL_NEW_CHAT_BUTTON", "")
    NEW_CHAT_LABELS: list = [
        s.strip() for s in os.getenv(
            "NEW_CHAT_LABELS", "New chat,Новый чат,Создать чат,新对话,Nouvelle conversation"
        ).split(",") if s.strip()
    ]
    SEL_LOGIN_FORM_MARKER: str = os.getenv("SEL_LOGIN_FORM_MARKER", "form")
    SEL_MESSAGE_ITEM: str = os.getenv(
        "SEL_MESSAGE_ITEM", "div[class*='ds-message']:not([class*='main-content'])"
    )
    SEL_MESSAGE_EDIT_BUTTON: str = os.getenv(
        "SEL_MESSAGE_EDIT_BUTTON", "button[class*='edit'], div[class*='edit'], [aria-label*='Edit']"
    )
    SEL_MESSAGE_EDIT_INPUT: str = os.getenv("SEL_MESSAGE_EDIT_INPUT", "textarea")
    SEL_MESSAGE_EDIT_SAVE: str = os.getenv(
        "SEL_MESSAGE_EDIT_SAVE", "button:has-text('Save'), button[type='submit']"
    )
    SEL_REGENERATE_BUTTON: str = os.getenv(
        "SEL_REGENERATE_BUTTON",
        "xpath=//div[@role='button' and .//*[local-name()='path'][starts-with(@d, 'M7.92136')]]",
    )
    VALIDATION_URL: str = os.getenv("VALIDATION_URL", "")

    # DeepSeek External Search & Summarizer
    SEARCH_API_URL: str = os.getenv("SEARCH_API_URL", "")
    SEARCH_API_KEY: str = os.getenv("SEARCH_API_KEY", "")
    SEARCH_RESULTS_LIMIT: int = int(os.getenv("SEARCH_RESULTS_LIMIT", "5"))
    SUMMARIZER_API_URL: str = os.getenv("SUMMARIZER_API_URL", "")
    SUMMARIZER_API_KEY: str = os.getenv("SUMMARIZER_API_KEY", "")
    SUMMARIZER_MODEL: str = os.getenv("SUMMARIZER_MODEL", "gpt-4o-mini")
    SUMMARIZER_MODEL_FALLBACKS: list = [
        s.strip() for s in os.getenv("SUMMARIZER_MODEL_FALLBACKS", "").split(",") if s.strip()
    ]
    SUMMARIZE_THRESHOLD_CHARS: int = int(os.getenv("SUMMARIZE_THRESHOLD_CHARS", "30000"))

    DEEP_THINK_PREFIX: str = os.getenv(
        "DEEP_THINK_PREFIX",
        "Пожалуйста, поразмысли над вопросом пошагово, взвесь альтернативы и только затем дай итоговый развёрнутый ответ.\n\n",
    )
    SYSTEM_PROMPT_TEMPLATE: str = os.getenv(
        "SYSTEM_PROMPT_TEMPLATE",
        "SYSTEM INSTRUCTION:\n{system}\n\n"
        "Follow the SYSTEM INSTRUCTION above for this and all subsequent "
        "responses. Now the user asks:\n\n{user}",
    )

    MODE_TOGGLES: dict = {}
    for _pair in os.getenv(
        "MODE_TOGGLES",
        "deepseek-chat:0:0,deepseek-think:1:0,"
        "deepseek-search:0:1,deepseek-think-search:1:1,"
        "deepseek-reasoner:1:0,deepseek-r1:1:0",
    ).split(","):
        if ":" in _pair:
            _name, _d, _s = _pair.split(":")
            MODE_TOGGLES[_name.strip().lower()] = (bool(int(_d)), bool(int(_s)))

    # ----------------- Qwen Engine -----------------
    QWEN_BASE_URL: str = os.getenv("QWEN_BASE_URL", "https://chat.qwen.ai")
    SESSION_DIR: str = str(SYS_ROOT / os.getenv("SESSION_DIR", "./session"))
    QWEN_RATE_LIMIT_HOURS: int = int(os.getenv("QWEN_RATE_LIMIT_HOURS", "24"))
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")

    @staticmethod
    def get_timeout(base_ms: int) -> float:
        return _jitter(base_ms)

    def update_api_key(self, new_key: str) -> None:
        self.API_KEY = new_key.strip()
        os.environ["API_KEY"] = self.API_KEY
        try:
            set_key(str(ENV_PATH), "API_KEY", self.API_KEY)
        except Exception:
            pass


settings = Settings()

# Ensure necessary directories exist
Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.USER_DATA_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.SESSION_DIR).mkdir(parents=True, exist_ok=True)
