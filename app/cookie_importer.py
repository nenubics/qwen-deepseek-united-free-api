"""
Universal Auto-Cookie Importer and Session Synchronizer.
Supports:
- JSON arrays (Cookie-Editor, EditThisCookie, Playwright)
- Netscape / Mozilla cookies.txt format
- Raw HTTP 'Cookie: name=val; name2=val2' header strings
- Automatic provider detection (DeepSeek vs. Qwen)
- Auto-extraction of Qwen JWT tokens from cookies
- Local filesystem auto-scanning (Downloads, Desktop, workspace)
- Direct SQLite and file-based session injection
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from app.config import settings
from app.deepseek.crypto_store import session_store
from app.qwen import token_manager

logger = logging.getLogger("cookie_importer")


def parse_cookies_any(raw: str, default_domain: str = "") -> List[Dict[str, Any]]:
    """
    Parses cookies from any format: JSON, Netscape, or raw HTTP header.
    Returns normalized list of cookie dicts.
    """
    raw = raw.strip().lstrip("\ufeff")
    if not raw:
        return []

    # 1. Try JSON
    if (raw.startswith("[") and raw.endswith("]")) or (raw.startswith("{") and raw.endswith("}")):
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                if "cookies" in data and isinstance(data["cookies"], list):
                    data = data["cookies"]
                elif "origins" in data:  # Playwright storageState
                    cookies = []
                    for origin in data.get("origins", []):
                        cookies.extend(origin.get("cookies", []))
                    if cookies:
                        data = cookies
            if isinstance(data, list):
                result = []
                for item in data:
                    if not isinstance(item, dict) or not item.get("name"):
                        continue
                    cookie = {
                        "name": str(item.get("name")),
                        "value": str(item.get("value", "")),
                        "domain": str(item.get("domain") or default_domain or ""),
                        "path": str(item.get("path") or "/"),
                        "secure": bool(item.get("secure", False)),
                        "httpOnly": bool(item.get("httpOnly", False)),
                    }
                    exp = item.get("expirationDate") or item.get("expires")
                    if exp:
                        try:
                            cookie["expires"] = int(float(exp))
                        except Exception:
                            pass
                    same_site = item.get("sameSite")
                    if same_site and isinstance(same_site, str):
                        cookie["sameSite"] = same_site.capitalize()
                    result.append(cookie)
                if result:
                    return result
        except json.JSONDecodeError:
            pass

    # 2. Try Netscape / Mozilla format
    netscape: List[Dict[str, Any]] = []
    lines = raw.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("# ") or (line.startswith("#") and not line.startswith("#HttpOnly_")):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            domain = parts[0]
            http_only = False
            if domain.startswith("#HttpOnly_"):
                domain = domain[len("#HttpOnly_"):]
                http_only = True
            path = parts[2]
            secure = parts[3].strip().lower() == "true"
            expires = parts[4].strip()
            name = parts[5].strip()
            value = parts[6].strip()
            
            cookie = {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path or "/",
                "secure": secure,
                "httpOnly": http_only,
            }
            if expires.isdigit() and int(expires) > 0:
                cookie["expires"] = int(expires)
            netscape.append(cookie)

    if netscape:
        return netscape

    # 3. Try HTTP Header format: "Cookie: name=val; name2=val2" or "name=val; name2=val2"
    clean_header = re.sub(r"(?i)^\s*cookie:\s*", "", raw).strip()
    header_cookies: List[Dict[str, Any]] = []
    
    # Split by semicolon or newline
    pairs = re.split(r"[;\n]\s*", clean_header)
    for pair in pairs:
        pair = pair.strip()
        if "=" not in pair or pair.startswith("#"):
            continue
        name, _, value = pair.partition("=")
        name = name.strip()
        value = value.strip()
        # Remove trailing semicolon or quotes if present
        if value.endswith(";"):
            value = value[:-1].strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]

        if not name:
            continue

        cookie = {
            "name": name,
            "value": value,
            "domain": default_domain or "",
            "path": "/",
            "secure": True,
            "httpOnly": False,
        }
        header_cookies.append(cookie)

    return header_cookies


def detect_cookie_provider(cookies: List[Dict[str, Any]], raw_text: str = "") -> str:
    """
    Analyzes cookies to determine if they belong to 'deepseek', 'qwen', or 'unknown'.
    """
    text = (raw_text + " " + " ".join(f"{c.get('domain','')} {c.get('name','')}" for c in cookies)).lower()

    has_deepseek = (
        "deepseek.com" in text
        or "userToken" in [c.get("name") for c in cookies]
        or "ds_session" in [c.get("name") for c in cookies]
        or "intercom-session" in [c.get("name") for c in cookies]
    )

    has_qwen = (
        "qwen.ai" in text
        or "tongyi" in text
        or "aliyun" in text
        or "login_aliyunid_ticket" in [c.get("name") for c in cookies]
        or "login_aliyunid_pk" in [c.get("name") for c in cookies]
        or "qwen_session" in [c.get("name") for c in cookies]
    )

    if has_deepseek and not has_qwen:
        return "deepseek"
    if has_qwen and not has_deepseek:
        return "qwen"
    if has_deepseek and has_qwen:
        return "both"

    # Fallback inspection: check for JWT in values
    for c in cookies:
        val = c.get("value", "")
        if val.startswith("ey") and len(val) > 80:
            return "qwen"

    return "unknown"


def extract_jwt_tokens(cookies: List[Dict[str, Any]], raw_text: str = "") -> List[str]:
    """
    Finds potential JWT tokens in cookie values or raw input text.
    """
    tokens = []
    jwt_pattern = re.compile(r"ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")

    for m in jwt_pattern.finditer(raw_text):
        tokens.append(m.group(0))

    for c in cookies:
        val = c.get("value", "")
        for m in jwt_pattern.finditer(val):
            tokens.append(m.group(0))

    return list(dict.fromkeys(tokens))


def format_as_netscape(cookies: List[Dict[str, Any]]) -> str:
    """Serializes cookie dicts into standard Netscape cookies.txt format."""
    lines = [
        "# Netscape HTTP Cookie File",
        "# Exported by Unified Qwen + DeepSeek API Auto-Cookie Engine",
        "",
    ]
    for c in cookies:
        domain = c.get("domain", "") or ".deepseek.com"
        if not domain.startswith(".") and not domain.startswith("http"):
            domain = "." + domain
        if c.get("httpOnly"):
            domain = "#HttpOnly_" + domain
        tailmatch = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path") or "/"
        secure = "TRUE" if c.get("secure") else "FALSE"
        expires = str(c.get("expires") or int(time.time() + 365 * 86400))
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append(f"{domain}\t{tailmatch}\t{path}\t{secure}\t{expires}\t{name}\t{value}")
    return "\n".join(lines) + "\n"


def apply_cookies_to_deepseek(
    cookies: List[Dict[str, Any]],
    profile_name: str = "default",
) -> Dict[str, Any]:
    """
    Saves cookies to COOKIE_FILE and encrypts them into SQLite session_store.
    Also ensures proper domain mapping for deepseek.com.
    """
    if not cookies:
        return {"success": False, "error": "No cookies provided."}

    # Normalize domain to .deepseek.com if missing
    for c in cookies:
        if not c.get("domain") or c.get("domain") in ("", "."):
            c["domain"] = ".deepseek.com"

    # 1. Save to COOKIE_FILE
    cookie_file_path = Path(settings.COOKIE_FILE)
    cookie_file_path.parent.mkdir(parents=True, exist_ok=True)
    netscape_text = format_as_netscape(cookies)
    cookie_file_path.write_text(netscape_text, encoding="utf-8")

    # Also save as cookies.json next to it
    json_path = cookie_file_path.with_suffix(".json")
    try:
        json_path.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
    except Exception:
        pass

    # 2. Encrypt & save in SQLite session store
    try:
        session_store.save_session(
            profile_id=profile_name,
            cookies=cookies,
            local_storage={},
        )
    except Exception as e:
        logger.warning(f"Failed to update SQLite session store: {e}")

    logger.info(f"Applied {len(cookies)} cookies to DeepSeek profile '{profile_name}'")
    return {
        "success": True,
        "provider": "deepseek",
        "profile": profile_name,
        "cookie_count": len(cookies),
        "names": [c.get("name") for c in cookies[:10]],
        "cookie_file": str(cookie_file_path),
    }


def apply_cookies_to_qwen(
    cookies: List[Dict[str, Any]],
    raw_text: str = "",
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Saves cookies and token to session/tokens.json for Qwen API client.
    """
    # Normalize domain to .qwen.ai if missing
    for c in cookies:
        if not c.get("domain"):
            c["domain"] = ".qwen.ai"

    # Search for JWT token in text or cookies
    jwt_tokens = extract_jwt_tokens(cookies, raw_text)
    token = jwt_tokens[0] if jwt_tokens else None

    # Check if there's an existing token in token_manager to preserve
    if not token:
        existing_tokens = token_manager.load_tokens()
        if existing_tokens:
            token = existing_tokens[0].get("token")

    if not token:
        # Fallback dummy/placeholder token if user only provided raw session cookies
        token = f"cookie_auth_{int(time.time())}"

    account_id = f"qwen_cookie_{int(time.time() * 1000) % 1000000}"
    # Check if ticket cookie exists
    ticket_cookie = next((c for c in cookies if "ticket" in c.get("name", "").lower()), None)
    if ticket_cookie:
        account_id = f"qwen_{ticket_cookie.get('value', '')[:10]}"

    acc = token_manager.add_or_update_token(
        token_str=token,
        account_id=account_id,
        label=label or "auto_cookie_imported",
        cookies=cookies,
    )

    logger.info(f"Applied {len(cookies)} cookies to Qwen account '{acc.get('id')}'")
    return {
        "success": True,
        "provider": "qwen",
        "account_id": acc.get("id"),
        "cookie_count": len(cookies),
        "has_jwt": bool(jwt_tokens),
        "names": [c.get("name") for c in cookies[:10]],
    }


def apply_cookies(
    raw_content: str,
    target_provider: str = "auto",
    profile_name: str = "default",
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unified entry point: parses raw cookies, determines provider, and applies.
    """
    cookies = parse_cookies_any(raw_content)
    if not cookies:
        return {"success": False, "error": "Could not parse any cookies from provided input."}

    detected = detect_cookie_provider(cookies, raw_content)
    provider = target_provider.lower()
    if provider == "auto":
        provider = detected if detected != "unknown" else "deepseek"

    results = {}

    if provider in ("deepseek", "both"):
        ds_res = apply_cookies_to_deepseek(cookies, profile_name=profile_name)
        results["deepseek"] = ds_res

    if provider in ("qwen", "both"):
        qw_res = apply_cookies_to_qwen(cookies, raw_text=raw_content, label=label)
        results["qwen"] = qw_res

    return {
        "success": True,
        "provider": provider,
        "detected_provider": detected,
        "total_parsed_cookies": len(cookies),
        "details": results,
    }


def scan_local_cookie_files() -> List[Dict[str, Any]]:
    """
    Scans common user folders for exported cookie files (.txt, .json).
    """
    found_files = []
    search_dirs = [
        Path("."),
        Path("./data"),
        Path("./session"),
        Path.home() / "Downloads",
        Path.home() / "Desktop",
    ]

    patterns = [
        "cookies*.txt",
        "*deepseek*.txt",
        "*qwen*.txt",
        "cookies*.json",
        "*deepseek*.json",
        "*qwen*.json",
    ]

    seen = set()
    for directory in search_dirs:
        if not directory.exists():
            continue
        try:
            for pattern in patterns:
                for file_path in directory.glob(pattern):
                    if file_path.is_file() and str(file_path.resolve()) not in seen:
                        seen.add(str(file_path.resolve()))
                        size = file_path.stat().st_size
                        if size > 0 and size < 5 * 1024 * 1024:  # Under 5MB
                            try:
                                content = file_path.read_text(encoding="utf-8", errors="ignore")
                                cookies = parse_cookies_any(content[:20000])
                                if cookies:
                                    prov = detect_cookie_provider(cookies, content[:2000])
                                    found_files.append({
                                        "path": str(file_path.resolve()),
                                        "filename": file_path.name,
                                        "size_bytes": size,
                                        "detected_provider": prov,
                                        "cookie_count": len(cookies),
                                        "modified_at": file_path.stat().st_mtime,
                                    })
                            except Exception:
                                pass
        except Exception as e:
            logger.debug(f"Error scanning directory {directory}: {e}")

    return sorted(found_files, key=lambda x: x["modified_at"], reverse=True)


def auto_import_from_scanned_files() -> Dict[str, Any]:
    """
    Scans for cookie files and automatically imports the most relevant ones.
    """
    files = scan_local_cookie_files()
    if not files:
        return {"success": False, "message": "No cookie export files found in workspace or Downloads."}

    imported = []
    for f in files:
        prov = f.get("detected_provider")
        if prov in ("deepseek", "qwen", "both"):
            try:
                content = Path(f["path"]).read_text(encoding="utf-8", errors="ignore")
                res = apply_cookies(content, target_provider=prov)
                imported.append({
                    "file": f["filename"],
                    "path": f["path"],
                    "provider": prov,
                    "result": res,
                })
            except Exception as e:
                logger.warning(f"Error importing from {f['path']}: {e}")

    if imported:
        return {
            "success": True,
            "imported_count": len(imported),
            "files": imported,
            "message": f"Successfully auto-imported cookies from {len(imported)} file(s).",
        }
    else:
        return {
            "success": False,
            "message": f"Found {len(files)} files, but none contained valid DeepSeek or Qwen cookies.",
            "candidates": files,
        }
