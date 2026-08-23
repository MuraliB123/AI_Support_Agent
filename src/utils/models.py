"""Chat model factory (DeepSeek)."""

from __future__ import annotations

import os
from functools import lru_cache

from langchain_deepseek import ChatDeepSeek

from src.utils.config import get_deepseek_api_key, get_model_config


@lru_cache(maxsize=1)
def get_chat_model() -> ChatDeepSeek:
    """Return the configured DeepSeek chat model used by all graph nodes."""
    cfg = get_model_config()["chat"]
    get_deepseek_api_key()  # fail fast with a clear message if the key is missing
    return ChatDeepSeek(
        model=os.getenv("DEEPSEEK_MODEL", cfg["model"]),
        temperature=cfg.get("temperature", 0.0),
        max_tokens=cfg.get("max_tokens"),
        max_retries=cfg.get("max_retries", 2),
        timeout=cfg.get("timeout_seconds"),
    )
