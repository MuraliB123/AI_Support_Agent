"""Shared utilities."""

from src.utils.config import (
    get_app_config,
    get_model_config,
    get_mongodb_uri,
    get_routing_rules,
)

__all__ = [
    "get_app_config",
    "get_model_config",
    "get_routing_rules",
    "get_mongodb_uri",
    "get_chat_model",
    "get_embeddings",
]


def __getattr__(name: str):
    # Lazy: avoid importing torch/langchain until model factories are used
    if name in {"get_chat_model", "get_embeddings"}:
        from src.utils import models as _models

        return getattr(_models, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
