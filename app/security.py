"""
Security, Authentication and Rate Limiting Middleware.
Supports 1 Unified API Key for all models and clients.
"""

import logging
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger("security")


def openai_error(status: int, message: str, etype: str = "invalid_request_error", code: str = "") -> JSONResponse:
    err = {"message": message, "type": etype}
    if code:
        err["code"] = code
    return JSONResponse(status_code=status, content={"error": err})


class SlidingWindowLimiter:
    """In-memory sliding window rate limiter per client IP."""

    def __init__(self, limit_per_minute: int = 120, window_seconds: float = 60.0):
        self.limit = max(0, int(limit_per_minute))
        self.window = max(1.0, float(window_seconds))
        self._hits: Dict[str, Deque[float]] = {}

    def check(self, ip: str) -> Tuple[bool, float]:
        if self.limit <= 0 or settings.DISABLE_RATE_LIMIT:
            return True, 0.0
        now = time.time()
        dq = self._hits.get(ip)
        if dq is None:
            dq = self._hits[ip] = deque()
        while dq and dq[0] <= now - self.window:
            dq.popleft()
        if len(dq) >= self.limit:
            return False, max(1.0, dq[0] + self.window - now)
        dq.append(now)
        if len(self._hits) > 4096:
            for key in [k for k, v in list(self._hits.items()) if not v]:
                del self._hits[key]
        return True, 0.0


def extract_api_key(request: Request) -> Optional[str]:
    """Extract API key from Authorization header, X-API-Key header, or query param."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    if auth.startswith("bearer "):
        return auth[7:].strip()

    x_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    if x_key:
        return x_key.strip()

    query_key = request.query_params.get("api_key")
    if query_key:
        return query_key.strip()

    return None


def is_auth_exempt(path: str) -> bool:
    """Check if the given path is exempt from API key authentication."""
    # Static & Web Dashboard
    if path in ("/", "/dashboard", "/ui", "/favicon.ico"):
        return True
    if path.startswith("/static/") or path.startswith("/dashboard/"):
        return True
    # Health checks
    if path in ("/health", "/healthz", "/api/health", "/api/status"):
        return True
    return False


def install_security(app: FastAPI, limiter: Optional[SlidingWindowLimiter] = None) -> None:
    """Install unified authentication and access logging middleware."""

    @app.middleware("http")
    async def unified_auth_middleware(request: Request, call_next):
        path = request.url.path

        # Always allow OPTIONS for CORS
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check if auth required
        active_key = settings.API_KEY.strip() if settings.API_KEY else ""

        if active_key and not is_auth_exempt(path):
            # Only enforce on /v1/*, /api/chat/*, /api/images/*, /api/videos/*, /api/models, etc.
            is_protected_api = (
                path.startswith("/v1/")
                or path == "/api/chat"
                or path.startswith("/api/chat/")
                or path.startswith("/api/models")
                or path.startswith("/api/images")
                or path.startswith("/api/videos")
                or path.startswith("/api/files")
            )

            if is_protected_api:
                provided_key = extract_api_key(request)
                if not provided_key or provided_key != active_key:
                    return openai_error(
                        401,
                        "Неверный API ключ (Invalid API key). Provide header 'Authorization: Bearer <API_KEY>'",
                        "invalid_request_error",
                        "invalid_api_key",
                    )

        return await call_next(request)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        path = request.url.path
        skip = path in ("/healthz", "/health", "/api/health", "/favicon.ico")

        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            status = 500
            logger.exception(f"Unhandled exception during {request.method} {path}")
            raise
        finally:
            if not skip:
                ip = request.client.host if request.client else "unknown"
                elapsed_ms = round((time.time() - start) * 1000, 2)
                level = logging.ERROR if status >= 400 else logging.INFO
                logger.log(
                    level,
                    f"[{request.method}] {path} -> {status} ({elapsed_ms}ms) from {ip}",
                )

        return response
