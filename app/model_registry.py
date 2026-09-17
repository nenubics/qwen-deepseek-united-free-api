"""
Unified Model Registry for Qwen & DeepSeek.
Single source of truth for model definitions, aliases, and provider routing.
"""

from typing import Dict, List, Optional, Tuple, Any

# ----------------------------------------------------------------------
# DEEPSEEK MODELS
# ----------------------------------------------------------------------
# model -> (deep_think, search)
DEEPSEEK_TOGGLES: Dict[str, Tuple[bool, bool]] = {
    "deepseek-chat": (False, False),
    "deepseek-think": (True, False),
    "deepseek-reasoner": (True, False),
    "deepseek-r1": (True, False),
    "deepseek-search": (False, True),
    "deepseek-think-search": (True, True),
}

DEEPSEEK_METADATA: Dict[str, Dict[str, Any]] = {
    "deepseek-chat": {
        "display_name": "DeepSeek V3 Chat",
        "description": "Standard fast mode for dialogue and text generation.",
        "capabilities": ["chat"],
    },
    "deepseek-think": {
        "display_name": "DeepSeek R1 (DeepThink)",
        "description": "Chain-of-thought reasoning mode with reasoning_content output.",
        "capabilities": ["chat", "reasoning"],
    },
    "deepseek-reasoner": {
        "display_name": "DeepSeek Reasoner (R1)",
        "description": "Alias for deepseek-think, matching official DeepSeek API.",
        "capabilities": ["chat", "reasoning"],
    },
    "deepseek-r1": {
        "display_name": "DeepSeek R1",
        "description": "Direct alias for DeepSeek R1 reasoning.",
        "capabilities": ["chat", "reasoning"],
    },
    "deepseek-search": {
        "display_name": "DeepSeek Search",
        "description": "DeepSeek Chat with active real-time web search and citation sources.",
        "capabilities": ["chat", "search"],
    },
    "deepseek-think-search": {
        "display_name": "DeepSeek Think + Search",
        "description": "Dual mode combining deep chain-of-thought reasoning with web search.",
        "capabilities": ["chat", "reasoning", "search"],
    },
}

# ----------------------------------------------------------------------
# QWEN MODELS
# ----------------------------------------------------------------------
QWEN_CANONICAL_MODELS = [
    "qwen3.7-max",
    "qwen3.7-plus",
    "qwen3.6-plus",
    "qwen3.5-plus",
    "qwen3.5-flash",
    "qwen3.5-397b-a17b",
    "qwen3.5-122b-a10b",
    "qwen3.5-27b",
    "qwen3.5-35b-a3b",
    "qwen3-max",
    "qwen3-vl-plus",
    "qwen3-coder-plus",
    "qwen3-omni-flash",
    "qwen3-omni-flash-2025-12-01",
    "qwen-max-latest",
    "qwen-plus-2025-09-11",
    "qwen-plus-2025-01-25",
    "qwq-32b",
    "qwen3-235b-a22b",
    "qwen3-30b-a3b",
    "qwen3-coder-30b-a3b-instruct",
    "qwen-turbo-2025-02-11",
    "qwen2.5-omni-7b",
    "qvq-72b-preview-0310",
    "qwen2.5-vl-32b-instruct",
    "qwen2.5-14b-instruct-1m",
    "qwen2.5-coder-32b-instruct",
    "qwen2.5-72b-instruct",
]

QWEN_METADATA: Dict[str, Dict[str, Any]] = {
    "qwen3.7-max": {
        "display_name": "Qwen 3.7 Max",
        "description": "Flagship Qwen model with top reasoning, multilingual, and general intelligence.",
        "capabilities": ["chat", "reasoning"],
    },
    "qwen3.7-plus": {
        "display_name": "Qwen 3.7 Plus",
        "description": "High-efficiency balanced Qwen 3.7 tier.",
        "capabilities": ["chat"],
    },
    "qwen3.6-plus": {
        "display_name": "Qwen 3.6 Plus",
        "description": "Qwen 3.6 high capability generation model.",
        "capabilities": ["chat"],
    },
    "qwen3.5-plus": {
        "display_name": "Qwen 3.5 Plus",
        "description": "Fast and versatile everyday assistant model.",
        "capabilities": ["chat"],
    },
    "qwen3.5-flash": {
        "display_name": "Qwen 3.5 Flash",
        "description": "Ultra fast low-latency Qwen response tier.",
        "capabilities": ["chat"],
    },
    "qwen3-max": {
        "display_name": "Qwen 3 Max",
        "description": "Qwen 3 top performance reasoning model.",
        "capabilities": ["chat"],
    },
    "qwen3-vl-plus": {
        "display_name": "Qwen 3 VL Plus (Vision)",
        "description": "Vision-language multimodal model for image understanding and t2i.",
        "capabilities": ["chat", "vision"],
    },
    "qwen3-coder-plus": {
        "display_name": "Qwen 3 Coder Plus",
        "description": "Specialized coding and programming assistant.",
        "capabilities": ["chat", "code"],
    },
    "qwq-32b": {
        "display_name": "QwQ 32B (Reasoning)",
        "description": "Qwen specialized open reasoning model rivaling OpenAI o1.",
        "capabilities": ["chat", "reasoning"],
    },
    "qvq-72b-preview-0310": {
        "display_name": "QVQ 72B (Visual Reasoning)",
        "description": "Multimodal visual reasoning model.",
        "capabilities": ["chat", "vision", "reasoning"],
    },
    "qwen2.5-coder-32b-instruct": {
        "display_name": "Qwen 2.5 Coder 32B",
        "description": "State-of-the-art code generation and refactoring instruct model.",
        "capabilities": ["chat", "code"],
    },
    "qwen2.5-72b-instruct": {
        "display_name": "Qwen 2.5 72B Instruct",
        "description": "Solid open-weights 72B instruction-following workhorse.",
        "capabilities": ["chat"],
    },
}

QWEN_ALIASES: Dict[str, str] = {
    # 3.7
    "qwen3.7": "qwen3.7-plus",
    "qwen-3.7-max": "qwen3.7-max",
    "qwen-3.7-plus": "qwen3.7-plus",
    "qwen37-max": "qwen3.7-max",
    "qwen37max": "qwen3.7-max",
    "qwen37-plus": "qwen3.7-plus",
    # 3.6
    "qwen3.6": "qwen3.6-plus",
    "qwen-3.6-plus": "qwen3.6-plus",
    "qwen36-plus": "qwen3.6-plus",
    # 3.5
    "qwen3.5": "qwen3.5-plus",
    "qwen-3.5-plus": "qwen3.5-plus",
    # Max
    "qwen-max": "qwen3-max",
    "qwen-max-latest": "qwen-max-latest",
    # Coder
    "qwen-coder": "qwen3-coder-plus",
    "qwen-coder-plus": "qwen3-coder-plus",
    "qwen3-coder": "qwen3-coder-plus",
    # VL / Vision
    "qwen-vl": "qwen3-vl-plus",
    "qwen-vl-plus": "qwen3-vl-plus",
    "qwen-vl-max": "qwen3-vl-plus",
    # Reasoning
    "qwq": "qwq-32b",
    "qvq": "qvq-72b-preview-0310",
    # Generic
    "qwen": "qwen3.7-max",
    "qwen-turbo": "qwen-turbo-2025-02-11",
    "qwen-plus": "qwen3.7-plus",
}


def detect_provider(model_name: Optional[str]) -> str:
    """
    Detect whether the requested model is for DeepSeek or Qwen.
    Defaults to Qwen or DeepSeek based on prefix/name.
    """
    if not model_name:
        return "qwen"
    clean = model_name.strip().lower()

    if clean.startswith("deepseek") or clean in DEEPSEEK_TOGGLES:
        return "deepseek"

    if clean.startswith("qwen") or clean.startswith("qwq") or clean.startswith("qvq") or clean.startswith("wan"):
        return "qwen"

    # Check aliases
    if clean in QWEN_ALIASES or clean in QWEN_CANONICAL_MODELS:
        return "qwen"

    # Default fallback: if has 'deepseek' anywhere -> deepseek, else qwen
    if "deepseek" in clean:
        return "deepseek"
    return "qwen"


def get_mapped_model(model_name: Optional[str], default_model: str = "qwen3.7-max") -> str:
    """
    Resolve aliases into canonical model name.
    """
    if not model_name:
        return default_model
    clean = model_name.strip().lower()

    # DeepSeek aliases
    if clean in ("deepseek-reasoner", "deepseek-r1"):
        return "deepseek-think"
    if clean in DEEPSEEK_TOGGLES:
        return clean

    # Qwen aliases
    if clean in QWEN_ALIASES:
        return QWEN_ALIASES[clean]
    for canon in QWEN_CANONICAL_MODELS:
        if canon.lower() == clean:
            return canon

    return model_name


def list_all_models() -> List[Dict[str, Any]]:
    """
    Returns OpenAI-compatible model list containing both DeepSeek and Qwen models.
    """
    models = []

    # 1. Add DeepSeek models
    for model_id, (think, search) in DEEPSEEK_TOGGLES.items():
        meta = DEEPSEEK_METADATA.get(model_id, {})
        models.append({
            "id": model_id,
            "object": "model",
            "created": 1700000000,
            "owned_by": "deepseek",
            "provider": "deepseek",
            "display_name": meta.get("display_name", model_id),
            "description": meta.get("description", "DeepSeek browser-based proxy mode."),
            "capabilities": meta.get("capabilities", ["chat"]),
            "deep_think": think,
            "search": search,
        })

    # 2. Add Qwen models
    for model_id in QWEN_CANONICAL_MODELS:
        meta = QWEN_METADATA.get(model_id, {})
        models.append({
            "id": model_id,
            "object": "model",
            "created": 1710000000,
            "owned_by": "qwen",
            "provider": "qwen",
            "display_name": meta.get("display_name", model_id),
            "description": meta.get("description", "Qwen Chat model."),
            "capabilities": meta.get("capabilities", ["chat"]),
        })

    return models
