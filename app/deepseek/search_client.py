"""
Search client for external web queries.
"""

import httpx
from app.config import settings


async def search_web(query: str) -> str:
    if not settings.SEARCH_API_URL:
        return ""

    headers = {}
    if settings.SEARCH_API_KEY:
        headers["Authorization"] = f"Bearer {settings.SEARCH_API_KEY}"

    params = {"q": query, "limit": settings.SEARCH_RESULTS_LIMIT}
    timeout = httpx.Timeout(settings.get_timeout(15000) / 1000)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(settings.SEARCH_API_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            return f"[web search temporarily unavailable: {exc}]"

    items = data.get("results", [])[: settings.SEARCH_RESULTS_LIMIT]
    if not items:
        return ""

    lines = ["External Web Search Results:"]
    for i, item in enumerate(items, start=1):
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        lines.append(f"{i}. {title} — {snippet}")
    return "\n".join(lines)
