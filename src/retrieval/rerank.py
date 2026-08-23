"""Combine dense + sparse retrieval lists via reciprocal rank fusion (RRF)."""

from __future__ import annotations

from typing import Any

from src.utils.config import get_app_config, get_model_config

# Standard RRF constant from Cormack et al.; keeps top ranks dominant
RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]],
    *,
    id_key: str = "chunk_id",
    k: int = RRF_K,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Fuse several ranked result lists with Reciprocal Rank Fusion.

    ``score`` on the output is the fused RRF score. Original per-channel
    ranks are kept under ``rrf_ranks`` for debugging / learning.
    """
    cfg = get_app_config()["retrieval"]
    limit = limit if limit is not None else int(cfg.get("final_top_k", 10))

    scores: dict[str, float] = {}
    docs: dict[str, dict[str, Any]] = {}
    ranks: dict[str, dict[str, int]] = {}

    for list_idx, ranked in enumerate(ranked_lists):
        channel = f"list_{list_idx}"
        for rank, doc in enumerate(ranked, start=1):
            doc_id = doc.get(id_key)
            if not doc_id:
                continue
            channel_name = str(doc.get("channel") or channel)
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            if doc_id not in docs:
                docs[doc_id] = dict(doc)
            ranks.setdefault(doc_id, {})[channel_name] = rank
            # Prefer keeping the highest raw channel score seen
            prev = float(docs[doc_id].get("score") or 0.0)
            cur = float(doc.get("score") or 0.0)
            if cur > prev:
                docs[doc_id]["score"] = cur

    fused: list[dict[str, Any]] = []
    for doc_id, rrf_score in sorted(scores.items(), key=lambda kv: kv[1], reverse=True):
        hit = dict(docs[doc_id])
        hit["rrf_score"] = rrf_score
        hit["score"] = rrf_score
        hit["rrf_ranks"] = ranks.get(doc_id, {})
        hit["channel"] = "fused"
        fused.append(hit)
        if len(fused) >= limit:
            break

    return fused


def rerank(
    *,
    dense_results: list[dict[str, Any]],
    sparse_results: list[dict[str, Any]],
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Combine vector + keyword lists.

    Strategy comes from ``model_config.rerank`` (default: reciprocal_rank_fusion).
    """
    strategy = get_model_config().get("rerank", {}).get(
        "strategy", "reciprocal_rank_fusion"
    )
    cfg = get_app_config()["retrieval"]
    # Pull a wider pool into fusion, then cut to final_top_k
    pool = limit if limit is not None else int(cfg.get("rerank_top_n", 20))
    final_k = int(cfg.get("final_top_k", 10))

    if strategy != "reciprocal_rank_fusion":
        # Only RRF is implemented in Phase 4; fall through to RRF anyway
        pass

    fused = reciprocal_rank_fusion(
        [dense_results, sparse_results],
        limit=max(pool, final_k),
    )
    return fused[:final_k]
