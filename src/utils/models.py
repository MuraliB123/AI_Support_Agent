"""Model factories: DeepSeek chat + local BGE embeddings."""

from __future__ import annotations

import os
from functools import lru_cache

from langchain_deepseek import ChatDeepSeek
from langchain_huggingface import HuggingFaceEmbeddings

from src.utils.config import get_deepseek_api_key, get_model_config


@lru_cache(maxsize=1)
def get_chat_model() -> ChatDeepSeek:
    """Return configured DeepSeek chat model for LCEL / LangGraph nodes."""
    cfg = get_model_config()["chat"]
    model_name = os.getenv("DEEPSEEK_MODEL", cfg["model"])
    # Ensures key is present; ChatDeepSeek also reads DEEPSEEK_API_KEY
    get_deepseek_api_key()
    return ChatDeepSeek(
        model=model_name,
        temperature=cfg.get("temperature", 0.0),
        max_tokens=cfg.get("max_tokens"),
        max_retries=cfg.get("max_retries", 2),
        timeout=cfg.get("timeout_seconds"),
    )


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """Return local BGE embeddings (384-dim) for MongoDB Atlas vector search."""
    cfg = get_model_config()["embeddings"]
    return HuggingFaceEmbeddings(
        model_name=cfg["model"],
        encode_kwargs={"normalize_embeddings": cfg.get("normalize", True)},
    )
