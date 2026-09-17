"""
Unified Qwen & DeepSeek Free API Service.
Single API Key with Automatic Model Routing and Full Web Dashboard.
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app import __version__
from app.config import settings
from app.model_registry import (
    detect_provider,
    get_mapped_model,
    list_all_models,
)
from app.providers.deepseek_provider import (
    get_deepseek_status,
    handle_deepseek_completions,
    shutdown_deepseek,
    startup_deepseek,
)
from app.providers.qwen_provider import handle_qwen_completions
from app.qwen import (
    browser_auth,
    client as qwen_client,
    token_manager as qwen_tokens,
)
from app.schemas import (
    ChatCompletionRequest,
    ChatSwitchRequest,
    ImageGenerationRequest,
)
from app.security import (
    SlidingWindowLimiter,
    install_security,
    openai_error,
)
from app.cookie_importer import (
    apply_cookies,
    scan_local_cookie_files,
    auto_import_from_scanned_files,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("unified_api")

_started_at = time.time()
rate_limiter = SlidingWindowLimiter(limit_per_minute=settings.RATE_LIMIT_PER_MINUTE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("=" * 60)
    logger.info(f" Starting Unified Qwen & DeepSeek API Service v{__version__}")
    logger.info(f" Host: {settings.HOST}:{settings.PORT}")
    logger.info(f" Unified API Key: {'Enabled (' + settings.API_KEY[:6] + '...)' if settings.API_KEY else 'Disabled (Open Access)'}")
    logger.info(f" Default Model: {settings.DEFAULT_MODEL}")
    logger.info(f" Dashboard: http://{settings.HOST}:{settings.PORT}/dashboard")
    logger.info("=" * 60)

    # Initialize DeepSeek browser session pool in background so server starts immediately
    try:
        await startup_deepseek()
    except Exception as e:
        logger.warning(f"Notice on DeepSeek session pool startup: {e}. Browser will start when requested.")

    # Check Qwen accounts
    q_summary = qwen_tokens.get_accounts_summary()
    logger.info(f"Qwen Accounts loaded: {q_summary['total']} total ({q_summary['active']} active)")

    yield

    # Shutdown
    try:
        await shutdown_deepseek()
    except Exception as e:
        logger.warning(f"Error shutting down DeepSeek pool: {e}")


app = FastAPI(
    title="Unified Qwen & DeepSeek Free API",
    version=__version__,
    description="OpenAI-compatible unified proxy uniting FreeQwenApi and DeepSeek-Api-Free with 1 API key.",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS if settings.ALLOWED_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Unified Security & Access Logging
install_security(app, limiter=rate_limiter)

# Path to Dashboard
DASHBOARD_PATH = Path(__file__).resolve().parent / "dashboard" / "index.html"


# =====================================================================
# DASHBOARD & WEB UI
# =====================================================================
@app.get("/", include_in_schema=False)
@app.get("/dashboard", include_in_schema=False)
@app.get("/ui", include_in_schema=False)
async def serve_dashboard():
    if not DASHBOARD_PATH.exists():
        raise HTTPException(status_code=404, detail="Dashboard UI not found.")
    return FileResponse(DASHBOARD_PATH, media_type="text/html")


# =====================================================================
# CHAT COMPLETIONS (OPENAI COMPATIBLE)
# =====================================================================
@app.post("/v1/chat/completions")
@app.post("/api/chat/completions")
@app.post("/api/chat")
async def chat_completions(request: ChatCompletionRequest, http_request: Request):
    """
    Unified chat completions endpoint.
    Automatically routes to DeepSeek or Qwen based on requested model name!
    Both providers work with the same single API key.
    """
    # Rate limit check per IP
    if not settings.DISABLE_RATE_LIMIT:
        ip = http_request.client.host if http_request.client else "unknown"
        allowed, retry_after = rate_limiter.check(ip)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Please wait {int(retry_after) + 1} seconds.",
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

    model = request.model or settings.DEFAULT_MODEL
    provider = detect_provider(model)

    logger.info(f"Incoming chat request: model='{model}' -> provider='{provider}' (stream={request.stream})")

    if provider == "deepseek":
        return await handle_deepseek_completions(request, http_request)
    else:
        return await handle_qwen_completions(request, http_request)


@app.get("/v1/chat/completions")
@app.get("/api/chat/completions")
async def chat_completions_get():
    return JSONResponse(
        status_code=405,
        content={"error": {"message": "Method Not Allowed. Use POST /v1/chat/completions.", "type": "invalid_request_error"}},
    )


# =====================================================================
# MODELS CATALOG (OPENAI COMPATIBLE)
# =====================================================================
@app.get("/v1/models")
@app.get("/api/models")
async def list_models():
    """Returns union list of all available Qwen and DeepSeek models with metadata."""
    models = list_all_models()
    return {"object": "list", "data": models}


@app.get("/v1/models/{model_id:path}")
@app.get("/api/models/{model_id:path}")
async def get_model(model_id: str):
    models = list_all_models()
    for m in models:
        if m["id"] == model_id:
            return m
    raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")


# =====================================================================
# DEEPSEEK CONTROL ENDPOINTS
# =====================================================================
@app.post("/v1/chat/new")
async def deepseek_new_chat():
    from app.deepseek import browser_session, BrowserSessionError
    try:
        url = await browser_session.new_chat()
        chat_id = await browser_session.get_current_chat_id()
        return {"ok": True, "chat_id": chat_id, "url": url}
    except BrowserSessionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/v1/chat/list")
async def deepseek_list_chats():
    from app.deepseek import browser_session, BrowserSessionError
    try:
        chats = await browser_session.list_chats()
        return {"chats": chats}
    except BrowserSessionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/chat/switch")
async def deepseek_switch_chat(req: ChatSwitchRequest):
    from app.deepseek import browser_session, BrowserSessionError
    try:
        await browser_session.switch_chat(req.chat_id)
        return {"ok": True, "chat_id": req.chat_id}
    except BrowserSessionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/v1/chat/history")
async def deepseek_chat_history():
    from app.deepseek import browser_session, BrowserSessionError
    try:
        messages = await browser_session.get_history()
        return {"messages": messages}
    except BrowserSessionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/chat/stop")
async def deepseek_stop_generation():
    from app.deepseek import browser_session, BrowserSessionError
    try:
        content = await browser_session.stop_generation()
        return {"ok": True, "content": content}
    except BrowserSessionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# =====================================================================
# CHAT & TASK THREAD MANAGEMENT
# =====================================================================
@app.get("/api/chats")
@app.get("/v1/chats")
async def list_managed_chats(limit: int = 30):
    """Lists all intelligent managed chat sessions across Qwen and DeepSeek."""
    from app.chat_manager import chat_manager
    chats = chat_manager.list_chats(limit=limit)
    return {"ok": True, "chats": chats, "count": len(chats)}


@app.post("/api/chats/new")
@app.post("/v1/chats/new")
async def reset_active_chats():
    """Resets active thread affinity so the next prompt starts a fresh chat thread."""
    from app.chat_manager import chat_manager
    count = chat_manager.reset_all_active()
    return {"ok": True, "reset_count": count, "message": "All active task affinities reset. Next prompt will start a new chat thread."}


@app.post("/api/chats/{task_id}/active")
async def set_active_chat(task_id: str):
    """Sets an existing task thread as the active thread."""
    from app.chat_manager import chat_manager
    success = chat_manager.set_active(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task or chat not found.")
    return {"ok": True, "task_id": task_id, "message": "Task thread activated."}


@app.delete("/api/chats/{task_id}")
async def delete_managed_chat(task_id: str):
    """Deletes a managed chat session from registry."""
    from app.chat_manager import chat_manager
    success = chat_manager.delete_chat(task_id)
    return {"ok": success}


# =====================================================================
# QWEN MEDIA & IMAGE GENERATION
# =====================================================================
@app.post("/v1/images/generations")
@app.post("/api/images/generations")
async def generate_images(req: ImageGenerationRequest):
    """Text-to-Image generation via Qwen."""
    prompt = req.prompt
    model = req.model or "qwen3-vl-plus"
    size = req.aspect_ratio or req.size or "1:1"

    result = await qwen_client.generate_image_t2i(prompt=prompt, model=model, size=size)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Image generation failed."))

    image_url = result.get("imageUrl") or result.get("url")
    return {
        "created": int(time.time()),
        "data": [{"url": image_url}],
        "model": model,
        "prompt": prompt,
    }


@app.get("/api/images/models")
async def list_image_models():
    return {
        "data": [
            {"id": "qwen3-vl-plus", "name": "Qwen 3 VL Plus (Chat Native)", "provider": "qwen"},
            {"id": "qwen-image-plus", "name": "Qwen Image Plus (DashScope)", "provider": "qwen"},
            {"id": "qwen-image-max", "name": "Qwen Image Max (DashScope)", "provider": "qwen"},
            {"id": "wan2.5-t2i-preview", "name": "Wan 2.5 Text-to-Image", "provider": "qwen"},
        ]
    }


# =====================================================================
# DASHBOARD & MANAGEMENT API
# =====================================================================
@app.get("/health")
@app.get("/healthz")
@app.get("/api/health")
async def health_check():
    ds_status = await get_deepseek_status()
    qw_summary = qwen_tokens.get_accounts_summary()
    return {
        "status": "ok",
        "service": "Unified Qwen & DeepSeek API",
        "uptime": int(time.time() - _started_at),
        "version": __version__,
        "qwen": {"total_accounts": qw_summary["total"], "active": qw_summary["active"]},
        "deepseek": {"pool_sessions": ds_status.get("total", 0), "active": ds_status.get("active", 0)},
    }


@app.get("/api/status")
async def get_service_status():
    ds_status = await get_deepseek_status()
    qw_summary = qwen_tokens.get_accounts_summary()
    models = list_all_models()

    return {
        "ok": True,
        "version": __version__,
        "uptime": int(time.time() - _started_at),
        "default_model": settings.DEFAULT_MODEL,
        "api_key": {
            "enabled": bool(settings.API_KEY),
            "key": settings.API_KEY,
            "preview": f"{settings.API_KEY[:6]}...{settings.API_KEY[-4:]}" if len(settings.API_KEY) > 10 else settings.API_KEY,
        },
        "models_count": len(models),
        "deepseek": {
            "status": "ready" if ds_status.get("total", 0) > 0 else "uninitialized",
            "memory_mode": settings.MEMORY_MODE,
            "headless": settings.HEADLESS,
            "pool": ds_status,
        },
        "qwen": qw_summary,
    }


@app.post("/api/settings/api-key")
async def update_api_key(payload: Dict[str, Any]):
    new_key = payload.get("key", "").strip()
    settings.update_api_key(new_key)
    logger.info(f"API Key updated via Dashboard to: {'enabled' if new_key else 'disabled'}")
    return {"ok": True, "api_key": settings.API_KEY}


@app.post("/api/settings/default-model")
async def update_default_model(payload: Dict[str, Any]):
    new_model = payload.get("model", "").strip()
    if new_model:
        settings.DEFAULT_MODEL = new_model
    return {"ok": True, "default_model": settings.DEFAULT_MODEL}


@app.get("/api/accounts/qwen")
async def list_qwen_accounts():
    return qwen_tokens.get_accounts_summary()


@app.post("/api/accounts/qwen")
async def add_qwen_account(payload: Dict[str, Any]):
    token = payload.get("token", "").strip()
    label = payload.get("label", "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token cannot be empty.")

    acc = qwen_tokens.add_or_update_token(token_str=token, label=label)
    return {"ok": True, "account": acc}


@app.delete("/api/accounts/qwen/{account_id}")
async def delete_qwen_account(account_id: str):
    success = qwen_tokens.delete_account(account_id)
    return {"ok": success}


@app.post("/api/accounts/qwen/{account_id}/check")
async def check_qwen_account(account_id: str):
    tokens = qwen_tokens.load_tokens()
    acc = next((t for t in tokens if t.get("id") == account_id), None)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found.")

    chat_id = await qwen_client.create_qwen_chat(acc, "qwen3.7-plus")
    if chat_id:
        qwen_tokens.mark_valid(account_id)
        return {"ok": True, "status": "OK", "message": "Account successfully verified!"}
    else:
        return {"ok": False, "status": "INVALID", "message": "Failed to create chat. Token may be expired."}


@app.post("/api/accounts/qwen/{account_id}/label")
async def set_qwen_label(account_id: str, payload: Dict[str, Any]):
    label = payload.get("label", "").strip()
    success = qwen_tokens.set_label(account_id, label)
    return {"ok": success}


@app.post("/api/accounts/qwen/login")
async def trigger_qwen_login(payload: Dict[str, Any] = {}):
    """Launches visible browser for manual sign-in to Qwen."""
    email = payload.get("email")
    password = payload.get("password")

    # Run in thread or async background
    asyncio.create_task(
        browser_auth.login_qwen_interactive(email=email, password=password, headless=False)
    )
    return {"ok": True, "message": "Browser opened for Qwen authorization. Please complete login in the window."}


@app.get("/api/accounts/deepseek")
async def list_deepseek_profiles():
    status = await get_deepseek_status()
    return status


@app.post("/api/accounts/deepseek/login")
async def trigger_deepseek_login(payload: Dict[str, Any] = {}):
    """Launches visible browser for manual sign-in to DeepSeek."""
    from app.deepseek import browser_session

    async def _do_login():
        try:
            await browser_session.start(headless=False)
            logger.info("DeepSeek browser opened for login.")
        except Exception as e:
            logger.error(f"Error launching DeepSeek login: {e}")

    asyncio.create_task(_do_login())
    return {"ok": True, "message": "Browser opened for DeepSeek authorization. Please log into chat.deepseek.com in the window."}


# =====================================================================
# AUTO-COOKIE MANAGEMENT ENDPOINTS
# =====================================================================
@app.post("/api/cookies/add")
async def add_cookies_endpoint(payload: Dict[str, Any]):
    raw_cookies = payload.get("cookies", "").strip()
    provider = payload.get("provider", "auto").strip().lower()
    profile = payload.get("profile", "default").strip()
    label = payload.get("label", "cookie_import").strip()

    if not raw_cookies:
        raise HTTPException(status_code=400, detail="Cookies content cannot be empty.")

    res = apply_cookies(
        raw_content=raw_cookies,
        target_provider=provider,
        profile_name=profile,
        label=label,
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to parse cookies."))
    return res


@app.post("/api/cookies/upload")
async def upload_cookies_file(
    file: UploadFile = File(...),
    provider: str = Form("auto"),
    profile: str = Form("default"),
):
    content_bytes = await file.read()
    raw_cookies = content_bytes.decode("utf-8", errors="ignore")
    if not raw_cookies.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    res = apply_cookies(
        raw_content=raw_cookies,
        target_provider=provider,
        profile_name=profile,
        label=f"file_{file.filename}",
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to parse cookies."))
    return res


@app.get("/api/cookies/scan")
async def scan_cookies_endpoint():
    files = scan_local_cookie_files()
    return {"ok": True, "files": files, "count": len(files)}


@app.post("/api/cookies/scan-import")
async def auto_scan_import_endpoint():
    res = auto_import_from_scanned_files()
    return res


# Global exception handler for OpenAI format
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    etype = "invalid_request_error" if exc.status_code == 400 else "server_error"
    return openai_error(exc.status_code, str(exc.detail), etype)
