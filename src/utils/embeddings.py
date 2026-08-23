"""Local BGE embedding helpers."""

from __future__ import annotations

from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from src.utils.config import get_model_config


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    """Return BAAI/bge-small-en-v1.5 (384-dim, normalized)."""
    cfg = get_model_config()["embeddings"]
    return HuggingFaceEmbeddings(
        model_name=cfg["model"],
        encode_kwargs={"normalize_embeddings": cfg.get("normalize", True)},
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns one vector per input string."""
    if not texts:
        return []
    return get_embeddings().embed_documents(texts)


def embed_query(text: str) -> list[float]:
    """Embed a single search query (same model as document embeddings)."""
    return get_embeddings().embed_query(text)
