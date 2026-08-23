"""Retrieval graph node: expand → vector + keyword/metadata → rerank."""

from __future__ import annotations

from typing import Any

from src.queue import publish
from src.retrieval.expand import expand_query, expansion_to_dict
from src.retrieval.keyword_search import keyword_search
from src.retrieval.pipeline import citation_view
from src.retrieval.rerank import rerank
from src.retrieval.vector_search import multi_query_vector_search
from src.utils.config import get_app_config


def retrieve_policies(state: dict[str, Any]) -> dict[str, Any]:
    """
    LangGraph node that runs the hybrid retrieval pipeline step by step.

    Publishes: expanding_query → searching → reranking → retrieval_done
    """
    ticket_id = state["ticket_id"]
    subject = state.get("subject", "")
    context_summary = state.get("context_summary", "")
    cfg = get_app_config()["retrieval"]
    dense_k = int(cfg.get("dense_top_k", 12))
    sparse_k = int(cfg.get("sparse_top_k", 12))
    default_scope = cfg.get("default_scope") or "global"

    publish(
        ticket_id,
        "expanding_query",
        "Rewriting your request into search queries...",
    )
    expansion = expand_query(
        subject=subject,
        context_summary=context_summary,
        messages=state.get("messages", []),
    )
    expansion_dict = expansion_to_dict(expansion)

    queries = [expansion.search_query, *expansion.alternate_queries]
    queries = [q.strip() for q in queries if q and q.strip()]
    scopes = list(expansion.scopes) if expansion.scopes else [default_scope]

    publish(
        ticket_id,
        "searching",
        "Searching policies (vector + keyword filters)...",
        search_query=expansion.search_query,
        categories=list(expansion.categories),
        keywords=list(expansion.keywords),
    )

    dense = multi_query_vector_search(queries, limit=dense_k)
    sparse = keyword_search(
        keywords=list(expansion.keywords),
        query_text=expansion.search_query,
        categories=list(expansion.categories),
        policy_ids=list(expansion.policy_ids),
        scopes=scopes,
        limit=sparse_k,
        use_metadata_filter=True,
    )

    publish(
        ticket_id,
        "reranking",
        "Combining and ranking the best policy passages...",
        dense_hits=len(dense),
        sparse_hits=len(sparse),
    )
    fused = rerank(dense_results=dense, sparse_results=sparse)
    chunks = [citation_view(doc) for doc in fused]

    citations = [
        {
            "chunk_id": c.get("chunk_id"),
            "policy_id": c.get("policy_id"),
            "section_title": c.get("section_title"),
            "score": c.get("score"),
        }
        for c in chunks
    ]
    publish(
        ticket_id,
        "retrieval_done",
        f"Found {len(chunks)} policy passage(s) for review.",
        citations=citations,
        search_query=expansion.search_query,
    )

    return {
        "query_expansion": expansion_dict,
        "retrieved_chunks": chunks,
        "dense_hit_count": len(dense),
        "sparse_hit_count": len(sparse),
    }
