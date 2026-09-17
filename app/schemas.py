"""
OpenAI-compatible and service Pydantic schemas.
"""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class ChatImage(BaseModel):
    type: Literal["image_path", "image_base64", "image_url"] = "image_path"
    value: str


class ToolCallFunction(BaseModel):
    name: str
    arguments: str


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: ToolCallFunction


class ToolFunctionDef(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class Tool(BaseModel):
    type: Literal["function"] = "function"
    function: Union[ToolFunctionDef, Dict[str, Any]]


class ChatMessage(BaseModel):
    role: str
    content: Optional[Union[str, List[Any]]] = ""
    images: Optional[List[ChatImage]] = None
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None


class EditRequest(BaseModel):
    index: int
    content: str


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage] = Field(default_factory=list)
    stream: Optional[bool] = False
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 1.0

    # DeepSeek flags
    deep_think: Optional[bool] = None
    search: Optional[bool] = None
    regenerate: Optional[bool] = False
    edit: Optional[EditRequest] = None
    new_chat: Optional[bool] = False
    conversation_id: Optional[str] = None
    tools: Optional[List[Union[Tool, Dict[str, Any]]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None

    # Qwen flags / compatibility
    chat_id: Optional[str] = None
    chatId: Optional[str] = None
    parent_id: Optional[str] = None
    parentId: Optional[str] = None
    files: Optional[List[Any]] = None
    chatType: Optional[str] = None  # 't2t', 't2i', 't2v'
    size: Optional[str] = None
    systemMessage: Optional[str] = None


class ChoiceMessage(BaseModel):
    role: str = "assistant"
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None


class Choice(BaseModel):
    index: int = 0
    message: ChoiceMessage
    finish_reason: Optional[str] = "stop"
    citations: Optional[List[str]] = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    ds_token_counter: Optional[int] = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage = Field(default_factory=Usage)
    chatId: Optional[str] = None
    parentId: Optional[str] = None


class ChatSwitchRequest(BaseModel):
    chat_id: str


class ImageGenerationRequest(BaseModel):
    prompt: str
    model: Optional[str] = "qwen-image-plus"
    n: Optional[int] = 1
    size: Optional[str] = "1024*1024"
    aspect_ratio: Optional[str] = "1:1"
    negative_prompt: Optional[str] = None
