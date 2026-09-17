"""
DeepSeek Provider Engine.
Integrates browser session pool, reasoning extraction, streaming, and tool calls.
"""

import asyncio
import json
import logging
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.deepseek import (
    BrowserSession,
    BrowserSessionError,
    PoolExhaustedError,
    SessionPool,
    browser_session,
    load_profiles,
    search_web,
    summarize_text,
    SummarizerUnavailableError,
)
from app.model_registry import DEEPSEEK_TOGGLES
from app.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    ChoiceMessage,
    Tool,
    ToolCall,
    ToolCallFunction,
    Usage,
)

logger = logging.getLogger("provider.deepseek")

session_pool = SessionPool(
    cooldown_seconds=settings.POOL_COOLDOWN_SECONDS,
    max_wait_seconds=settings.POOL_MAX_WAIT_SECONDS,
)

EMPTY_ANSWER_NUDGE = (
    "Ответь обязательно текстом, кратко и по существу. "
    "Не вызывай инструменты повторно без крайней необходимости."
)
EMPTY_ANSWER_FALLBACK = (
    "⚠️ Модель вернула пустой ответ. Попробуйте переформулировать запрос "
    "или повторите его через несколько секунд."
)
MAX_EMPTY_RETRIES = 2

_SHELL_LANGS = {"", "bash", "sh", "shell", "zsh", "powershell", "pwsh", "ps", "cmd", "batch", "dos"}
_CMD_KEYWORDS = {
    "glob", "ls", "dir", "gci", "get-childitem", "echo", "cat", "type", "cd", "pwd",
    "git", "npm", "python", "py", "node", "ping", "curl", "irm", "invoke-webrequest",
    "cmd", "powershell", "get-location", "get-content", "set-location",
    "get-item", "resolve-path", "find", "tree", "where",
}
_CLIENT_CWD_RE = re.compile(
    r"(?:working\s*directory|workspace\s*(?:root\s*folder)?|current\s*directory|\bcwd\b)"
    r"\s*[:=]?\s*['\"]?(?P<path>[A-Za-z]:\\[^\r\n'\"<>|]+|/[^\r\n'\"<>|]+)",
    re.IGNORECASE,
)


def _sse_chunk(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _estimate_tokens(text: Any) -> int:
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    return max(1, len(text) // 4)


def _extract_last_user_message(messages: List[ChatMessage]) -> ChatMessage:
    for msg in reversed(messages):
        if msg.role == "user":
            return msg
    raise HTTPException(status_code=400, detail="В запросе отсутствует сообщение пользователя.")


def _last_significant_message(messages: List[ChatMessage]) -> Optional[ChatMessage]:
    for msg in reversed(messages):
        if msg.role in ("user", "tool"):
            return msg
    return None


def _flatten_conversation(messages: List[ChatMessage]) -> str:
    parts: List[str] = []
    for m in messages:
        if m.role == "system":
            continue
        text = m.content if isinstance(m.content, str) else ""
        if m.role == "user":
            parts.append(f"[user]\n{text}")
        elif m.role == "assistant":
            if m.tool_calls:
                for tc in m.tool_calls:
                    parts.append(f"[assistant -> вызов инструмента {tc.function.name}]\n{tc.function.arguments}")
            else:
                parts.append(f"[assistant]\n{text}")
        elif m.role == "tool":
            parts.append(f"[результат инструмента]\n{text}")
    return "\n\n".join(parts)


def _build_tool_instruction(tools: Optional[List[Any]]) -> str:
    if not tools:
        return ""
    work_dir = settings.WORK_DIR or os.getcwd()
    lines = [
        "Тебе доступны инструменты (function calling). Когда нужно вызвать инструмент, "
        "оформи вызов как ОДНУ СТРОКУ чистого JSON без markdown-оформления — НЕ оборачивай "
        "в ```json заборы, НЕ ставь переносы строк внутри JSON. Перед вызовом МОЖНО "
        "написать краткое пояснение, но сам JSON-вызов должен быть на отдельной строке:",
        '{"name": "<точное_имя_инструмента>", "arguments": { ... }}',
        "Имя инструмента должно быть ТОЧНО из списка ниже. Поле arguments — объект с параметрами по схеме.",
        f"Команды исполняются в рабочей директории проекта: {work_dir}",
        "Доступные инструменты:",
    ]
    for t in tools:
        fn = t.get("function") if isinstance(t, dict) else getattr(t, "function", None)
        if isinstance(fn, dict):
            name = fn.get("name")
            desc = fn.get("description", "")
            params = fn.get("parameters", {})
        else:
            name = getattr(fn, "name", None)
            desc = getattr(fn, "description", "")
            params = getattr(fn, "parameters", {})
        lines.append(f"- {name}: {desc} схема: {json.dumps(params, ensure_ascii=False)}")
    return "\n".join(lines)


def _fix_unescaped_quotes(s: str) -> str:
    out = []
    in_string = False
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if in_string:
            if c == "\\":
                out.append(c)
                if i + 1 < n:
                    out.append(s[i + 1])
                    i += 2
                    continue
                i += 1
                continue
            if c == '"':
                j = i + 1
                while j < n and s[j] in " \t\r\n":
                    j += 1
                nxt = s[j] if j < n else ""
                if nxt in ",}:]":
                    out.append(c)
                    in_string = False
                else:
                    out.append('\\"')
                i += 1
                continue
            out.append(c)
            i += 1
            continue
        if c == '"':
            out.append(c)
            in_string = True
            i += 1
            continue
        out.append(c)
        i += 1
        continue
    return "".join(out)


def _safe_json_loads(s: str):
    try:
        return json.loads(s)
    except Exception:
        pass
    t = s.replace("```json", "").replace("```", "").replace("<tool_call>", "").replace("</tool_call>", "")
    t = t.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    t = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r'\\\\', t)
    t = re.sub(r'"([^"]*?)\s*"\s*:', r'"\1":', t)
    t = _fix_unescaped_quotes(t)
    try:
        return json.loads(t)
    except Exception:
        return None


def _extract_json_objects(text: str):
    objs = []
    start = None
    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                obj = _safe_json_loads(text[start:i + 1])
                if isinstance(obj, dict):
                    objs.append((start, i + 1, obj))
                start = None
    return objs


def _looks_like_command(body: str) -> bool:
    first = body.split(None, 1)[0].lower() if body else ""
    return first in _CMD_KEYWORDS


def _cmd_to_toolcall(body: str, tool_names: set):
    if "glob" in tool_names and re.match(r"glob\b", body, re.IGNORECASE):
        mg = re.match(r'glob\s+(?:-[A-Za-z]+\s+)?["\']?([^"\'\n]+?)["\']?\s*$', body, re.IGNORECASE)
        if mg:
            return {"name": "glob", "arguments": {"pattern": mg.group(1).strip()}}
    if "bash" in tool_names:
        return {"name": "bash", "arguments": {"command": body}}
    return None


def _canonical_call(call: dict) -> tuple:
    try:
        args = call.get("arguments") or {}
        if isinstance(args, str):
            args = _safe_json_loads(args) or {}
        s = json.dumps(args, sort_keys=True, ensure_ascii=False)
    except Exception:
        s = ""
    return (call.get("name"), s)


def _executed_calls(messages) -> set:
    has_result = any(getattr(m, "role", None) == "tool" for m in messages)
    if not has_result:
        return set()
    executed = set()
    for m in messages:
        if getattr(m, "role", None) == "assistant" and getattr(m, "tool_calls", None):
            for tc in m.tool_calls:
                fn = tc.function
                executed.add(_canonical_call({"name": fn.name, "arguments": fn.arguments}))
    return executed


def _last_tool_result(messages) -> Optional[str]:
    for m in reversed(messages):
        if getattr(m, "role", None) == "tool":
            c = m.content
            return c if isinstance(c, str) else ""
    return None


def _extract_client_cwd(messages) -> Optional[str]:
    if not messages:
        return None
    for m in messages:
        if getattr(m, "role", None) != "system":
            continue
        c = getattr(m, "content", None)
        text = ""
        if isinstance(c, str):
            text = c
        elif isinstance(c, list):
            text = "\n".join(
                p.get("text", "") for p in c
                if isinstance(p, dict) and p.get("type") == "text"
            )
        if not text:
            continue
        m = _CLIENT_CWD_RE.search(text)
        if m:
            return m.group("path").rstrip("\\/")
    return None


def _anchor_tool_cwd(tool_calls: list, cwd: Optional[str]) -> list:
    if not cwd:
        return tool_calls
    for tc in tool_calls:
        if tc.get("name") == "bash":
            args = tc.get("arguments")
            if not isinstance(args, dict):
                continue
            cmd = args.get("command")
            if isinstance(cmd, str) and cmd.strip():
                args["command"] = f'cd "{cwd}"\n{cmd}'
    return tool_calls


def _prune_loop_calls(parsed: list, messages) -> tuple:
    executed = _executed_calls(messages)
    if not executed:
        return parsed, False
    filtered = [c for c in parsed if _canonical_call(c) not in executed]
    return filtered, (bool(parsed) and not filtered)


def _tool_names(tools: Optional[List[Any]]) -> set:
    names: set = set()
    for t in tools or []:
        fn = t.get("function") if isinstance(t, dict) else getattr(t, "function", None)
        if isinstance(fn, dict):
            n = fn.get("name")
        else:
            n = getattr(fn, "name", None)
        if n:
            names.add(n)
    return names


def _safe_parse_tool_call(text: str, tools: Optional[List[Any]]):
    try:
        return _parse_tool_call(text, tools)
    except Exception as exc:
        logger.warning(f"Error parsing tool_call: {exc}")
        return [], text


def _parse_tool_call(text: str, tools: Optional[List[Any]]):
    if not tools:
        return [], text

    def _as_args(obj):
        args = obj.get("arguments", {})
        if isinstance(args, str):
            parsed = _safe_json_loads(args)
            args = parsed if isinstance(parsed, dict) else {}
        return args if isinstance(args, dict) else {}

    candidates = []
    for m in re.finditer(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL):
        candidates.append((m.start(1), m.end(1), m.group(1)))
    for m in re.finditer(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", text, re.DOTALL):
        candidates.append((m.start(1), m.end(1), m.group(1)))
    for s, e, obj in _extract_json_objects(text):
        candidates.append((s, e, obj))

    found = []
    for s, e, raw in candidates:
        obj = raw if isinstance(raw, dict) else None
        if obj is None:
            obj = _safe_json_loads(raw)
            if obj is None:
                continue
        if not isinstance(obj, dict):
            continue
        name = obj.get("name") or (obj.get("function") or {}).get("name")
        args = _as_args(obj)
        if name and isinstance(args, dict):
            found.append((s, e, name, args))

    seen = set()
    unique = []
    for s, e, n, a in found:
        if (s, e) in seen:
            continue
        seen.add((s, e))
        unique.append((s, e, n, a))
    found = unique

    if found:
        stripped = text
        for s, e, _, _ in sorted(found, key=lambda x: x[0], reverse=True):
            stripped = stripped[:s] + stripped[e:]
        stripped = (
            stripped.replace("```json", "")
            .replace("```", "")
            .replace("<tool_call>", "")
            .replace("</tool_call>", "")
            .strip()
        )
        calls = [{"name": n, "arguments": a} for _, _, n, a in found]
        return calls, stripped

    # Fallback: single name + arguments regex
    m_name = re.search(r'"name"\s*:\s*"([^"]*)"', text)
    if m_name:
        name = m_name.group(1)
        m_arg = re.search(r'arguments\s*"?\s*:\s*', text)
        if m_arg:
            rest = text[m_arg.end():].lstrip()
            args = None
            if rest.startswith("{"):
                objs = _extract_json_objects(rest)
                if objs and isinstance(objs[0][2], dict):
                    args = objs[0][2]
            if isinstance(args, dict):
                return [{"name": name, "arguments": args}], text

    tool_names = _tool_names(tools)
    if tool_names & {"bash", "glob"}:
        m_block = re.search(r"```(\w*)\n(.*?)\n```", text, re.DOTALL)
        if not m_block:
            m_block = re.search(r"```(\w*)\s*(.*?)\s*```", text, re.DOTALL)
        if m_block:
            lang = m_block.group(1).lower()
            body = m_block.group(2).strip()
            if body and not body.lstrip().startswith("{"):
                if lang in _SHELL_LANGS or _looks_like_command(body):
                    call = _cmd_to_toolcall(body, tool_names)
                    if call:
                        stripped = (text[:m_block.start()] + text[m_block.end():]).strip()
                        return [call], stripped
    return [], text


def _save_images_to_tmp(message: ChatMessage) -> List[str]:
    import base64
    paths: List[str] = []
    if not message.images:
        return paths

    tmp_dir = Path(tempfile.mkdtemp(prefix="chat_upload_"))
    for i, image in enumerate(message.images):
        if image.type == "image_path":
            paths.append(image.value)
        elif image.type == "image_base64":
            file_path = tmp_dir / f"image_{i}.png"
            file_path.write_bytes(base64.b64decode(image.value))
            paths.append(str(file_path))
        elif image.type == "image_url":
            raise HTTPException(
                status_code=400,
                detail="image_url is not supported directly for DeepSeek. Provide image_base64 or image_path.",
            )
    return paths


async def _maybe_summarize(conv: str) -> str:
    limit = settings.SUMMARIZE_THRESHOLD_CHARS
    if not settings.SUMMARIZER_API_URL or len(conv) <= limit:
        return conv
    head_len, tail_len = 2000, max(2000, limit - 2000)
    head, tail = conv[:head_len], conv[-tail_len:]
    middle = conv[head_len:len(conv) - tail_len]
    if not middle.strip():
        return conv
    try:
        summary = await summarize_text(
            middle,
            api_url=settings.SUMMARIZER_API_URL,
            api_key=settings.SUMMARIZER_API_KEY,
            model=settings.SUMMARIZER_MODEL,
            fallbacks=settings.SUMMARIZER_MODEL_FALLBACKS,
        )
    except SummarizerUnavailableError as exc:
        logger.warning(f"Summarizer unavailable: {exc}")
        return conv
    return head + "\n\n[Summary of earlier conversation]:\n" + summary + "\n\n[...conversation continuation...]\n" + tail


async def startup_deepseek() -> None:
    profiles = load_profiles(settings.USER_DATA_DIR, settings.COOKIE_FILE)
    p0 = profiles[0]
    browser_session.bind_profile(
        p0.user_data_dir or settings.USER_DATA_DIR,
        p0.cookie_file or settings.COOKIE_FILE,
    )
    owners = []
    for p in profiles:
        if p is p0:
            session_pool.add(p.name, browser_session)
            owners.append((p, browser_session))
        else:
            owner = BrowserSession(
                user_data_dir=p.user_data_dir or settings.USER_DATA_DIR,
                cookie_file=p.cookie_file or settings.COOKIE_FILE,
            )
            session_pool.add(p.name, owner)
            owners.append((p, owner))
    logger.info(f"Starting DeepSeek session pool ({len(session_pool)} profiles)...")
    await session_pool.start_all()

    for p, owner in owners:
        ntabs = p.tabs if p.tabs > 1 else settings.TABS_PER_PROFILE
        for i in range(2, ntabs + 1):
            try:
                tab = await BrowserSession.attach(owner)
                session_pool.add(f"{p.name}#tab{i}", tab)
            except Exception as exc:
                logger.warning(f"Failed to open tab {i} for profile '{p.name}': {exc}")
    logger.info(f"DeepSeek pool ready: total sessions {len(session_pool)}.")


async def shutdown_deepseek() -> None:
    logger.info("Closing DeepSeek session pool...")
    await session_pool.close_all()


async def get_deepseek_status() -> Dict[str, Any]:
    if len(session_pool):
        return await session_pool.get_status_summary()
    return {"total": 0, "active": 0, "cooling": 0, "profiles": []}


async def handle_deepseek_completions(
    request: ChatCompletionRequest, http_request: Request
) -> Union[StreamingResponse, ChatCompletionResponse]:
    """Handles /v1/chat/completions specifically for DeepSeek models."""
    if not request.regenerate and request.edit is None and not request.messages:
        raise HTTPException(status_code=400, detail="The 'messages' field is required.")

    try:
        sess = await session_pool.acquire(timeout=settings.REQUEST_QUEUE_TIMEOUT)
    except PoolExhaustedError as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": str(exc.retry_after)})

    eff_deep_think = request.deep_think
    eff_search = request.search
    model_key = (request.model or "").strip().lower()

    if model_key in settings.MODE_TOGGLES:
        eff_deep_think, eff_search = settings.MODE_TOGGLES[model_key]
    elif model_key in DEEPSEEK_TOGGLES:
        eff_deep_think, eff_search = DEEPSEEK_TOGGLES[model_key]

    async def _source(nudge: bool = False):
        msgs = request.messages
        if nudge and msgs:
            msgs = list(msgs) + [ChatMessage(role="user", content=EMPTY_ANSWER_NUDGE)]

        if request.regenerate:
            async for kind, delta in sess.regenerate_stream(chat_id=request.conversation_id):
                yield kind, delta
        elif request.edit is not None:
            async for kind, delta in sess.edit_stream(request.edit.index, request.edit.content, chat_id=request.conversation_id):
                yield kind, delta
        else:
            tools = request.tools
            system_msgs = [m for m in msgs if m.role == "system"]
            system_text = system_msgs[-1].content if system_msgs else ""
            last_user = _extract_last_user_message(msgs)
            mode = settings.MEMORY_MODE

            if mode == "client":
                conv = await _maybe_summarize(_flatten_conversation(msgs))
                tool_instr = _build_tool_instruction(tools) if tools else ""
                sys_part = system_text
                if tool_instr:
                    sys_part = (sys_part + "\n\n" + tool_instr).strip() if sys_part else tool_instr
                prompt = settings.SYSTEM_PROMPT_TEMPLATE.format(system=sys_part, user=conv) if sys_part else conv
                file_paths = _save_images_to_tmp(last_user)
                await sess.new_chat()
                async for kind, delta in sess.stream_message(
                    prompt,
                    file_paths,
                    deep_think=eff_deep_think,
                    search=eff_search,
                    chat_id=None,
                ):
                    yield kind, delta
            else:
                last = _last_significant_message(msgs)
                tool_instr = _build_tool_instruction(tools) if tools else ""
                if last and last.role == "tool":
                    prompt = "[tool result]\n" + (last.content if isinstance(last.content, str) else "")
                    if tool_instr:
                        prompt = settings.SYSTEM_PROMPT_TEMPLATE.format(system=tool_instr, user=prompt)
                else:
                    prompt = last_user.content if isinstance(last_user.content, str) else ""
                    sys_part = system_text
                    if tool_instr:
                        sys_part = (sys_part + "\n\n" + tool_instr).strip() if sys_part else tool_instr
                    if sys_part:
                        prompt = settings.SYSTEM_PROMPT_TEMPLATE.format(system=sys_part, user=prompt)
                file_paths = _save_images_to_tmp(last_user)
                if request.new_chat:
                    await sess.new_chat()
                async for kind, delta in sess.stream_message(
                    prompt,
                    file_paths,
                    deep_think=eff_deep_think,
                    search=eff_search,
                    chat_id=request.conversation_id,
                ):
                    yield kind, delta

    async def _finalize_usage(prompt_tokens: int, completion_tokens: int):
        ds_counter = None
        try:
            tc = await sess.extract_token_counts()
            if tc:
                ds_counter = f"{tc[0]}/{tc[1]}"
                return tc[0], ds_counter
        except Exception:
            pass
        return prompt_tokens + completion_tokens, ds_counter

    if request.stream:
        chat_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())
        prompt_tokens = sum(_estimate_tokens(m.content) for m in (request.messages or []))

        async def event_generator():
            try:
                yield _sse_chunk({
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": request.model,
                    "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                })

                final_text = ""
                final_tool_calls = []
                completion_tokens = 0
                attempt = 0
                while True:
                    acc_text = ""
                    acc_reason = ""
                    comp_tok = 0
                    stream_incremental = not request.tools
                    try:
                        async for kind, delta in _source(nudge=(attempt > 0)):
                            if kind == "reasoning":
                                if stream_incremental:
                                    yield _sse_chunk({
                                        "id": chat_id,
                                        "object": "chat.completion.chunk",
                                        "created": created,
                                        "model": request.model,
                                        "choices": [{"index": 0, "delta": {"reasoning_content": delta}, "finish_reason": None}],
                                    })
                            else:
                                comp_tok += _estimate_tokens(delta)
                                acc_text += delta
                                if stream_incremental:
                                    yield _sse_chunk({
                                        "id": chat_id,
                                        "object": "chat.completion.chunk",
                                        "created": created,
                                        "model": request.model,
                                        "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                                    })
                    except BrowserSessionError as exc:
                        await session_pool.mark_failed(sess)
                        yield _sse_chunk({"error": {"message": str(exc), "type": "server_error"}})
                        return
                    except Exception as exc:
                        logger.exception("Streaming generation error")
                        yield _sse_chunk({"error": {"message": f"Internal error: {exc}", "type": "server_error"}})
                        return

                    tool_calls = []
                    if request.tools and acc_text:
                        parsed, stripped = _safe_parse_tool_call(acc_text, request.tools)
                        if parsed:
                            parsed = _anchor_tool_cwd(
                                parsed, settings.WORK_DIR or _extract_client_cwd(request.messages)
                            )
                            parsed, looped_all = _prune_loop_calls(parsed, request.messages)
                            if looped_all:
                                last_res = _last_tool_result(request.messages)
                                acc_text = last_res or "Command result received."
                                tool_calls = []
                            else:
                                tool_calls = parsed
                                acc_text = stripped

                    if acc_text or tool_calls:
                        final_text, final_tool_calls = acc_text, tool_calls
                        completion_tokens = comp_tok
                        break

                    attempt += 1
                    if attempt > MAX_EMPTY_RETRIES:
                        final_text = EMPTY_ANSWER_FALLBACK
                        break

                total_tokens, ds_counter = await _finalize_usage(prompt_tokens, completion_tokens)
                conv_id = await sess.get_current_chat_id()
                citations = []
                if eff_search:
                    try:
                        citations = await sess.extract_citations()
                    except Exception:
                        citations = []

                if final_tool_calls:
                    if final_text:
                        yield _sse_chunk({
                            "id": chat_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": request.model,
                            "conversation_id": conv_id,
                            "choices": [{"index": 0, "delta": {"content": final_text}, "finish_reason": None}],
                        })
                    tc_delta = [
                        {
                            "index": i,
                            "id": f"call_{uuid.uuid4().hex[:12]}",
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"], ensure_ascii=False)},
                        }
                        for i, tc in enumerate(final_tool_calls)
                    ]
                    yield _sse_chunk({
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": request.model,
                        "conversation_id": conv_id,
                        "choices": [{"index": 0, "delta": {"tool_calls": tc_delta}, "finish_reason": None}],
                    })
                    yield _sse_chunk({
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": request.model,
                        "conversation_id": conv_id,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                        "usage": {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": total_tokens,
                            "ds_token_counter": ds_counter,
                        },
                        **({"citations": citations} if citations else {}),
                    })
                else:
                    if final_text and not stream_incremental:
                        yield _sse_chunk({
                            "id": chat_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": request.model,
                            "conversation_id": conv_id,
                            "choices": [{"index": 0, "delta": {"content": final_text}, "finish_reason": None}],
                        })
                    yield _sse_chunk({
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": request.model,
                        "conversation_id": conv_id,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        "usage": {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": total_tokens,
                            "ds_token_counter": ds_counter,
                        },
                        **({"citations": citations} if citations else {}),
                    })
                yield "data: [DONE]\n\n"
            finally:
                await session_pool.release(sess)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming mode
    try:
        try:
            response_text = ""
            reasoning_text = ""
            tool_calls_obj = None
            attempt = 0
            while True:
                rtext = ""
                rreason = ""
                async for kind, delta in _source(nudge=(attempt > 0)):
                    if kind == "reasoning":
                        rreason += delta
                    else:
                        rtext += delta

                parsed = []
                if request.tools and rtext:
                    parsed, stripped = _safe_parse_tool_call(rtext, request.tools)
                    if parsed:
                        parsed = _anchor_tool_cwd(
                            parsed, settings.WORK_DIR or _extract_client_cwd(request.messages)
                        )
                        parsed, looped_all = _prune_loop_calls(parsed, request.messages)
                        if looped_all:
                            last_res = _last_tool_result(request.messages)
                            rtext = last_res or "Command result received."
                            parsed = []
                        else:
                            rtext = stripped

                if rtext or parsed:
                    response_text = rtext
                    reasoning_text = rreason
                    if parsed:
                        tool_calls_obj = [
                            ToolCall(
                                id=f"call_{uuid.uuid4().hex[:12]}",
                                function=ToolCallFunction(
                                    name=tc["name"],
                                    arguments=json.dumps(tc["arguments"], ensure_ascii=False),
                                ),
                            )
                            for tc in parsed
                        ]
                    break

                attempt += 1
                if attempt > MAX_EMPTY_RETRIES:
                    response_text = EMPTY_ANSWER_FALLBACK
                    break

            if tool_calls_obj is None and sess._looks_busy(response_text):
                raise BrowserSessionError(
                    "DeepSeek is busy. Please wait a few seconds and try again."
                )
        except BrowserSessionError as exc:
            await session_pool.mark_failed(sess)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Error processing DeepSeek request")
            raise HTTPException(status_code=500, detail=f"Internal error: {exc}") from exc

        prompt_tokens = sum(_estimate_tokens(m.content) for m in (request.messages or []))
        completion_tokens = _estimate_tokens(response_text)
        total_tokens, ds_counter = await _finalize_usage(prompt_tokens, completion_tokens)
        conv_id = await sess.get_current_chat_id()

        citations = []
        if eff_search:
            try:
                citations = await sess.extract_citations()
            except Exception:
                citations = []

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4()}",
            created=int(time.time()),
            model=request.model or "deepseek-chat",
            choices=[Choice(
                index=0,
                message=ChoiceMessage(
                    content=(response_text if response_text else None),
                    reasoning_content=reasoning_text or None,
                    tool_calls=tool_calls_obj,
                ),
                finish_reason="tool_calls" if tool_calls_obj else "stop",
                citations=citations or None,
            )],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                ds_token_counter=ds_counter,
            ),
            chatId=conv_id,
        )
    finally:
        await session_pool.release(sess)
