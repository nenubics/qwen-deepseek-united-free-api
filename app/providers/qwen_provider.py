"""
Qwen Provider Engine.
Integrates Qwen API v2, multi-account rotation, streaming, and image generation.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.model_registry import get_mapped_model
from app.qwen import (
    build_qwen_payload,
    create_qwen_chat,
    execute_qwen_completion,
    generate_image_t2i,
    stream_qwen_openai_format,
    token_manager,
)
from app.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    ChoiceMessage,
    Usage,
)

logger = logging.getLogger("provider.qwen")


def _normalize_message_content(content: Any) -> Any:
    if not isinstance(content, list):
        return content

    normalized = []
    for item in content:
        if not isinstance(item, dict):
            normalized.append(item)
            continue

        item_type = item.get("type")
        if item_type == "text" and isinstance(item.get("text"), str):
            normalized.append({"type": "text", "text": item["text"]})
            continue
        if item_type == "image_url" and isinstance(item.get("image_url"), dict):
            image_url = item["image_url"].get("url")
            if image_url:
                normalized.append({"type": "image", "image": image_url})
                continue
        if item_type == "image" and isinstance(item.get("image"), str):
            normalized.append({"type": "image", "image": item["image"]})
            continue
        if item_type == "file" and isinstance(item.get("file"), str):
            normalized.append({"type": "file", "file": item["file"]})
            continue
        normalized.append(item)

    return normalized


def _extract_chat_and_parent_ids(request: ChatCompletionRequest) -> Tuple[Optional[str], Optional[str]]:
    chat_id = request.chatId or request.chat_id or request.conversation_id
    parent_id = request.parentId or request.parent_id
    return chat_id, parent_id


async def handle_qwen_completions(
    request: ChatCompletionRequest, http_request: Request
) -> Union[StreamingResponse, ChatCompletionResponse]:
    """Handles /v1/chat/completions specifically for Qwen models."""
    if not request.messages:
        raise HTTPException(status_code=400, detail="The 'messages' field is required.")

    token_info = token_manager.get_available_token()
    if not token_info:
        raise HTTPException(
            status_code=401,
            detail=(
                "No active Qwen accounts found. Please add a Qwen account in the Dashboard (/dashboard) "
                "or run 'python login.py --qwen' to authorize."
            ),
        )

    model_raw = request.model or settings.DEFAULT_MODEL
    mapped_model = get_mapped_model(model_raw)

    # Extract system and user messages
    messages = request.messages
    system_msg_obj = next((m for m in messages if m.role == "system"), None)
    system_msg = system_msg_obj.content if system_msg_obj and isinstance(system_msg_obj.content, str) else request.systemMessage

    user_msg_obj = next((m for m in reversed(messages) if m.role == "user"), None)
    if not user_msg_obj:
        raise HTTPException(status_code=400, detail="No user message found in 'messages'.")

    message_content = _normalize_message_content(user_msg_obj.content)
    files = request.files or []

    # Chat & Task Management: Reuse existing thread for the same task/theme
    from app.chat_manager import chat_manager
    existing_chat = chat_manager.resolve_chat(
        request, provider="qwen", http_headers=dict(http_request.headers)
    )

    if existing_chat:
        chat_id = existing_chat["chat_id"]
        parent_id = existing_chat.get("parent_id")
        logger.info(
            f"Continuing in existing Qwen chat {chat_id} (turn {existing_chat.get('message_count', 1) + 1}, parent: {parent_id}) for task '{existing_chat.get('title')}'"
        )
    else:
        chat_id, parent_id = _extract_chat_and_parent_ids(request)
        if not chat_id:
            chat_id = await create_qwen_chat(token_info, mapped_model)
            if not chat_id:
                raise HTTPException(status_code=502, detail="Failed to create Qwen conversation session.")
            chat_manager.register_chat(
                chat_id=chat_id,
                provider="qwen",
                model=mapped_model,
                messages=request.messages,
                parent_id=None,
            )

    payload = build_qwen_payload(
        message_content=message_content,
        model=mapped_model,
        chat_id=chat_id,
        parent_id=parent_id,
        system_message=system_msg,
        files=files,
        chat_type=request.chatType or "t2t",
        size=request.size,
    )

    if request.stream:
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Chat-Id": chat_id,
            "X-Conversation-Id": chat_id,
        }
        return StreamingResponse(
            stream_qwen_openai_format(token_info, chat_id, payload, mapped_model),
            media_type="text/event-stream",
            headers=headers,
        )

    # Non-streaming
    result = await execute_qwen_completion(token_info, chat_id, payload)
    if not result.get("success"):
        status_code = result.get("status") or 500
        if not isinstance(status_code, int) or status_code < 400:
            status_code = 500
        raise HTTPException(
            status_code=status_code,
            detail=result.get("details") or result.get("error") or "Qwen upstream error",
        )

    resp_parent_id = result.get("response_id") or parent_id
    try:
        chat_manager.record_turn(chat_id, new_parent_id=resp_parent_id)
    except Exception as e:
        logger.warning(f"Failed to record turn for Qwen chat {chat_id}: {e}")

    usage_dict = result.get("usage") or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4()}",
        created=int(time.time()),
        model=model_raw,
        choices=[Choice(
            index=0,
            message=ChoiceMessage(
                role="assistant",
                content=result.get("content", ""),
            ),
            finish_reason="stop",
        )],
        usage=Usage(
            prompt_tokens=usage_dict.get("prompt_tokens", 0),
            completion_tokens=usage_dict.get("completion_tokens", 0),
            total_tokens=usage_dict.get("total_tokens", 0),
        ),
        chatId=chat_id,
        parentId=resp_parent_id,
    )
