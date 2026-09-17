"""
Qwen Chat HTTP & Streaming Client.
Communicates directly with chat.qwen.ai API v2.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple

import httpx

from app.config import settings
from app.qwen import token_manager

logger = logging.getLogger("qwen.client")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
}

http_client = httpx.AsyncClient(timeout=120.0, follow_redirects=True)


def _apply_token_cookies(token_obj: Dict[str, Any]) -> None:
    if "cookies" in token_obj and isinstance(token_obj["cookies"], list):
        for cookie in token_obj["cookies"]:
            c_name = cookie.get("name")
            c_val = cookie.get("value")
            c_dom = cookie.get("domain") or "qwen.ai"
            if c_name and c_val:
                try:
                    http_client.cookies.set(c_name, c_val, domain=c_dom)
                except Exception:
                    pass


async def create_qwen_chat(token_obj: Dict[str, Any], model: str) -> Optional[str]:
    """Create a new conversation session on chat.qwen.ai."""
    token = token_obj.get("token")
    if not token:
        return None

    _apply_token_cookies(token_obj)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Accept": "*/*",
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Accept-Language": DEFAULT_HEADERS["Accept-Language"],
        "Origin": settings.QWEN_BASE_URL,
        "Referer": f"{settings.QWEN_BASE_URL}/",
    }
    payload = {
        "title": "New Chat",
        "models": [model],
        "chat_mode": "normal",
        "chat_type": "t2t",
        "timestamp": int(time.time() * 1000),
    }

    create_url = f"{settings.QWEN_BASE_URL}/api/v2/chats/new"
    try:
        resp = await http_client.post(create_url, headers=headers, json=payload, timeout=30.0)
        if resp.status_code == 200:
            data = resp.json()
            chat_id = data.get("data", {}).get("id")
            if chat_id:
                return str(chat_id)
        elif resp.status_code in (401, 403):
            logger.warning(f"Qwen token unauthorized ({resp.status_code}) on chat creation for {token_obj.get('id')}")
            token_manager.mark_invalid(token_obj.get("id"))
    except Exception as e:
        logger.error(f"Failed to create Qwen chat: {e}")
    return None


def build_qwen_payload(
    message_content: Any,
    model: str,
    chat_id: str,
    parent_id: Optional[str] = None,
    system_message: Optional[str] = None,
    files: Optional[List[Any]] = None,
    chat_type: str = "t2t",
    size: Optional[str] = None,
) -> Dict[str, Any]:
    user_msg_id = str(uuid.uuid4())
    assistant_msg_id = str(uuid.uuid4())

    sub_type = chat_type or "t2t"

    new_message = {
        "fid": user_msg_id,
        "parentId": parent_id,
        "parent_id": parent_id,
        "role": "user",
        "content": message_content,
        "chat_type": sub_type,
        "sub_chat_type": sub_type,
        "timestamp": int(time.time()),
        "user_action": "chat",
        "models": [model],
        "files": files or [],
        "childrenIds": [assistant_msg_id],
        "extra": {"meta": {"subChatType": sub_type}},
        "feature_config": {"thinking_enabled": False, "output_schema": "phase"},
    }

    if size and sub_type == "t2i":
        new_message["extra"]["size"] = size

    payload = {
        "stream": True,
        "incremental_output": True,
        "chat_id": chat_id,
        "chat_mode": "normal",
        "messages": [new_message],
        "model": model,
        "parent_id": parent_id,
        "timestamp": int(time.time()),
    }

    if system_message:
        payload["system_message"] = system_message

    return payload


async def execute_qwen_completion(
    token_obj: Dict[str, Any],
    chat_id: str,
    payload: Dict[str, Any],
    on_chunk: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    token = token_obj.get("token")
    acc_id = token_obj.get("id")

    _apply_token_cookies(token_obj)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Accept": "*/*",
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Accept-Language": DEFAULT_HEADERS["Accept-Language"],
        "Origin": settings.QWEN_BASE_URL,
        "Referer": f"{settings.QWEN_BASE_URL}/c/{chat_id}",
    }

    api_url = f"{settings.QWEN_BASE_URL}/api/v2/chat/completions?chat_id={chat_id}"
    logger.debug(f"Sending Qwen request to chat {chat_id} via {acc_id}...")

    try:
        async with http_client.stream(
            "POST",
            api_url,
            headers=headers,
            json=payload,
            timeout=120.0,
        ) as response:
            if response.status_code in (401, 403):
                token_manager.mark_invalid(acc_id)
                return {
                    "success": False,
                    "status": 401,
                    "error": "Qwen authorization expired or invalid",
                    "details": "Please re-login to Qwen Chat in dashboard",
                }

            if response.status_code != 200:
                body = (await response.aread()).decode("utf-8", errors="ignore")
                if "RateLimited" in body:
                    token_manager.mark_rate_limited(acc_id, settings.QWEN_RATE_LIMIT_HOURS)
                    return {"success": False, "status": 429, "error": "RateLimited", "details": body}
                return {"success": False, "status": response.status_code, "error": "Qwen upstream error", "details": body}

            content_type = (response.headers.get("content-type") or "").lower()

            # If Qwen returns plain JSON instead of SSE
            if "text/event-stream" not in content_type:
                body = (await response.aread()).decode("utf-8", errors="ignore")
                try:
                    parsed = json.loads(body)
                except Exception:
                    return {"success": False, "status": 500, "error": "Unexpected Qwen response", "details": body}

                if parsed.get("code") == "RateLimited":
                    token_manager.mark_rate_limited(acc_id, settings.QWEN_RATE_LIMIT_HOURS)
                    return {"success": False, "status": 429, "error": "RateLimited", "details": body}

                content = ""
                choices = parsed.get("choices")
                if isinstance(choices, list) and choices:
                    first = choices[0] if isinstance(choices[0], dict) else {}
                    msg = first.get("message") if isinstance(first.get("message"), dict) else {}
                    content = str(msg.get("content") or "")
                elif parsed.get("success") is True and isinstance(parsed.get("data"), dict):
                    content = str(parsed["data"].get("content") or "")

                if content and callable(on_chunk):
                    on_chunk(content)

                return {
                    "success": True,
                    "content": content,
                    "response_id": parsed.get("response_id") or parsed.get("id"),
                    "usage": parsed.get("usage") or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                }

            # Standard SSE streaming
            full_content = ""
            response_id = None
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

            async for raw_line in response.aiter_lines():
                line = raw_line.strip()
                if not line or not line.startswith("data:"):
                    continue

                data_str = line[5:].strip()
                if not data_str or data_str == "[DONE]":
                    break

                try:
                    chunk = json.loads(data_str)
                except Exception:
                    continue

                if chunk.get("code") == "RateLimited":
                    token_manager.mark_rate_limited(acc_id, settings.QWEN_RATE_LIMIT_HOURS)
                    return {"success": False, "status": 429, "error": "RateLimited", "details": json.dumps(chunk, ensure_ascii=False)}

                if chunk.get("response_id"):
                    response_id = chunk["response_id"]
                if isinstance(chunk.get("usage"), dict):
                    usage = chunk["usage"]

                choices = chunk.get("choices")
                if isinstance(choices, list) and choices:
                    first = choices[0] if isinstance(choices[0], dict) else {}
                    delta = first.get("delta") if isinstance(first.get("delta"), dict) else {}
                    piece = delta.get("content")
                    if piece is not None:
                        piece_str = str(piece)
                        full_content += piece_str
                        if callable(on_chunk):
                            on_chunk(piece_str)

                    if delta.get("status") == "finished" or first.get("finish_reason"):
                        break

            return {
                "success": True,
                "content": full_content,
                "response_id": response_id,
                "usage": usage,
            }

    except Exception as e:
        logger.error(f"Exception during Qwen request: {e}")
        return {"success": False, "status": 500, "error": "Proxy connection error", "details": str(e)}


async def stream_qwen_openai_format(
    token_info: Dict[str, Any],
    chat_id: str,
    payload: Dict[str, Any],
    model: str,
) -> AsyncGenerator[str, None]:
    """Generates standard OpenAI SSE chunks from Qwen stream."""
    queue: asyncio.Queue = asyncio.Queue()
    has_streamed = False

    def on_chunk(chunk_text: str):
        if chunk_text:
            queue.put_nowait(chunk_text)

    task = asyncio.create_task(
        execute_qwen_completion(token_info, chat_id, payload, on_chunk=on_chunk)
    )

    try:
        while True:
            if task.done() and queue.empty():
                break
            try:
                chunk = await asyncio.wait_for(queue.get(), timeout=0.15)
            except asyncio.TimeoutError:
                continue

            has_streamed = True
            yield "data: " + json.dumps({
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}],
            }, ensure_ascii=False) + "\n\n"

        result = await task
        if result.get("success"):
            try:
                from app.chat_manager import chat_manager
                chat_manager.record_turn(chat_id, new_parent_id=result.get("response_id"))
            except Exception as e:
                logger.warning(f"Failed to record turn for Qwen chat {chat_id}: {e}")
        elif not result.get("success"):
            if not has_streamed:
                err_text = f"Error: {result.get('error', 'Qwen API Error')}"
                yield "data: " + json.dumps({
                    "id": "chatcmpl-stream",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": err_text}, "finish_reason": None}],
                }, ensure_ascii=False) + "\n\n"
        elif not has_streamed and result.get("content"):
            yield "data: " + json.dumps({
                "id": "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{"index": 0, "delta": {"content": result["content"]}, "finish_reason": None}],
            }, ensure_ascii=False) + "\n\n"

        yield "data: " + json.dumps({
            "id": "chatcmpl-stream",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "conversation_id": chat_id,
            "chatId": chat_id,
        }, ensure_ascii=False) + "\n\n"
        yield "data: [DONE]\n\n"
    finally:
        if not task.done():
            task.cancel()


async def generate_image_t2i(prompt: str, model: str = "qwen3-vl-plus", size: str = "1:1") -> Dict[str, Any]:
    """Generates an image using Qwen Chat t2i mode."""
    token_info = token_manager.get_available_token()
    if not token_info:
        return {"success": False, "error": "No valid Qwen accounts available. Please log in."}

    chat_id = await create_qwen_chat(token_info, model)
    if not chat_id:
        return {"success": False, "error": "Failed to create Qwen image session"}

    payload = build_qwen_payload(
        message_content=prompt,
        model=model,
        chat_id=chat_id,
        chat_type="t2i",
        size=size,
    )

    result = await execute_qwen_completion(token_info, chat_id, payload)
    if result.get("success"):
        content = result.get("content", "")
        return {
            "success": True,
            "imageUrl": content,
            "url": content,
            "model": model,
            "prompt": prompt,
            "chatId": chat_id,
        }
    return result
