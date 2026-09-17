"""
Qwen Multi-Account Token & Session Manager.
Manages session/tokens.json, round-robin rotation, and account health.
"""

import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger("qwen.tokens")

_pointer = 0


def ensure_session_dir() -> Path:
    s_dir = Path(settings.SESSION_DIR)
    s_dir.mkdir(parents=True, exist_ok=True)
    return s_dir


def get_tokens_file() -> Path:
    return ensure_session_dir() / "tokens.json"


def decode_jwt_payload(token_str: str) -> Optional[Dict[str, Any]]:
    """Decodes JWT payload without signature verification for inspecting expiry/sub."""
    try:
        parts = token_str.strip().split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        # Pad base64
        padding = len(payload_b64) % 4
        if padding:
            payload_b64 += "=" * (4 - padding)
        decoded = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        return json.loads(decoded)
    except Exception:
        return None


def load_tokens() -> List[Dict[str, Any]]:
    tokens_file = get_tokens_file()
    if not tokens_file.exists():
        return []
    try:
        with open(tokens_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"Error loading tokens.json: {e}")
        return []


list_tokens = load_tokens


def save_tokens(tokens: List[Dict[str, Any]]) -> None:
    tokens_file = get_tokens_file()
    try:
        with open(tokens_file, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving tokens.json: {e}")


def get_available_token() -> Optional[Dict[str, Any]]:
    """Returns next valid token in round-robin sequence."""
    global _pointer
    tokens = load_tokens()
    if not tokens:
        return None

    now = time.time()
    valid = []
    for t in tokens:
        if t.get("invalid"):
            continue
        reset_at = t.get("resetAt")
        if reset_at:
            try:
                dt = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
                if dt.timestamp() > now:
                    continue  # still in cooldown
            except Exception:
                pass
        valid.append(t)

    if not valid:
        return None

    token_obj = valid[_pointer % len(valid)]
    _pointer = (_pointer + 1) % len(valid)
    return token_obj


def mark_rate_limited(account_id: str, hours: int = 24) -> None:
    tokens = load_tokens()
    now = time.time()
    for t in tokens:
        if t.get("id") == account_id:
            reset_dt = datetime.fromtimestamp(now + hours * 3600, tz=timezone.utc)
            t["resetAt"] = reset_dt.isoformat()
            break
    save_tokens(tokens)


def mark_invalid(account_id: str) -> None:
    tokens = load_tokens()
    for t in tokens:
        if t.get("id") == account_id:
            t["invalid"] = True
            break
    save_tokens(tokens)


def mark_valid(account_id: str, new_token: Optional[str] = None) -> None:
    tokens = load_tokens()
    for t in tokens:
        if t.get("id") == account_id:
            t["invalid"] = False
            t["resetAt"] = None
            if new_token:
                t["token"] = new_token
            break
    save_tokens(tokens)


def set_label(account_id: str, label: str) -> bool:
    tokens = load_tokens()
    found = False
    for t in tokens:
        if t.get("id") == account_id:
            t["label"] = label.strip()
            found = True
            break
    if found:
        save_tokens(tokens)
    return found


def delete_account(account_id: str) -> bool:
    tokens = load_tokens()
    new_tokens = [t for t in tokens if t.get("id") != account_id]
    if len(new_tokens) != len(tokens):
        save_tokens(new_tokens)
        return True
    return False


def add_or_update_token(
    token_str: str,
    account_id: Optional[str] = None,
    label: Optional[str] = None,
    cookies: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    raw_token = token_str.strip()
    if raw_token.lower().startswith("bearer "):
        raw_token = raw_token[7:].strip()

    jwt_data = decode_jwt_payload(raw_token)
    acc_id = account_id
    if not acc_id:
        if jwt_data and jwt_data.get("sub"):
            acc_id = f"qwen_{jwt_data['sub']}"
        else:
            acc_id = f"acc_{int(time.time() * 1000)}"

    tokens = load_tokens()
    existing = next((t for t in tokens if t.get("id") == acc_id), None)
    now_iso = datetime.now(timezone.utc).isoformat()

    if existing:
        existing["token"] = raw_token
        existing["invalid"] = False
        existing["resetAt"] = None
        if label is not None:
            existing["label"] = label
        if cookies:
            existing["cookies"] = cookies
        existing["updated_at"] = now_iso
    else:
        existing = {
            "id": acc_id,
            "label": label or "",
            "token": raw_token,
            "cookies": cookies or [],
            "added_at": now_iso,
            "updated_at": now_iso,
            "invalid": False,
            "resetAt": None,
        }
        tokens.append(existing)

    save_tokens(tokens)
    return existing


def get_accounts_summary() -> Dict[str, Any]:
    tokens = load_tokens()
    now = time.time()
    total = len(tokens)
    active = 0
    limited = 0
    invalid = 0

    acc_list = []
    for t in tokens:
        is_inv = bool(t.get("invalid"))
        is_lim = False
        reset_at = t.get("resetAt")
        if reset_at:
            try:
                dt = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
                if dt.timestamp() > now:
                    is_lim = True
            except Exception:
                pass

        if is_inv:
            status = "INVALID"
            invalid += 1
        elif is_lim:
            status = "WAIT"
            limited += 1
        else:
            status = "OK"
            active += 1

        token_preview = ""
        tk = t.get("token", "")
        if len(tk) > 16:
            token_preview = f"{tk[:6]}...{tk[-6:]}"

        acc_list.append({
            "id": t.get("id"),
            "label": t.get("label", ""),
            "status": status,
            "token_preview": token_preview,
            "resetAt": reset_at,
            "added_at": t.get("added_at"),
            "has_cookies": bool(t.get("cookies")),
        })

    return {
        "total": total,
        "active": active,
        "limited": limited,
        "invalid": invalid,
        "accounts": acc_list,
    }
