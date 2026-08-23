"""End-to-end retrieval: expand → vector → keyword/metadata → RRF rerank."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.retrieval.expand import QueryExpansion, expand_query, expansion_to_dict
from src.retrieval.keyword_search import keyword_search
from src.retrieval.rerank import rerank
from src.retrieval.vector_search import multi_query_vector_search
from src.utils.config import get_app_config


def citation_view(chunk: dict[str, Any]) -> dict[str, Any]:
    """Slim payload for graph state / later decision prompts."""
    return {
        "chunk_id": chunk.get("chunk_id"),
        "doc_id": chunk.get("doc_id"),
        "policy_id": chunk.get("policy_id"),
        "category": chunk.get("category"),
        "scope": chunk.get("scope"),
        "section_title": chunk.get("section_title"),
        "heading_path": chunk.get("heading_path") or [],
        "source_file": chunk.get("source_file"),
        "content": chunk.get("content"),
        "score": float(chunk.get("score") or 0.0),
        "rrf_score": float(chunk.get("rrf_score") or chunk.get("score") or 0.0),
        "rrf_ranks": chunk.get("rrf_ranks") or {},
        "channel": chunk.get("channel", "fused"),
    }


@dataclass
class RetrievalResult:
    expansion: dict[str, Any]
    dense_results: list[dict[str, Any]] = field(default_factory=list)
    sparse_results: list[dict[str, Any]] = field(default_factory=list)
    chunks: list[dict[str, Any]] = field(default_factory=list)

    def to_state_update(self) -> dict[str, Any]:
        return {
            "query_expansion": self.expansion,
            "retrieved_chunks": self.chunks,
            "dense_hit_count": len(self.dense_results),
            "sparse_hit_count": len(self.sparse_results),
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_retrieval_pipeline(
    *,
    subject: str,
    context_summary: str,
    messages: list[Any] | None = None,
    expansion: QueryExpansion | None = None,
) -> RetrievalResult:
    """
    Full Phase 4 pipeline.

    1. LLM query expansion (unless ``expansion`` is injected — tests)
    2. Atlas ``$vectorSearch`` over expanded queries
    3. Keyword / BM25 retrieval with metadata filters
    4. Reciprocal Rank Fusion → ``final_top_k``
    """
    cfg = get_app_config()["retrieval"]
    dense_k = int(cfg.get("dense_top_k", 12))
    sparse_k = int(cfg.get("sparse_top_k", 12))
    default_scope = cfg.get("default_scope") or "global"

    if expansion is None:
        expansion = expand_query(
            subject=subject,
            context_summary=context_summary,
            messages=messages,
        )

    queries = [expansion.search_query, *expansion.alternate_queries]
    queries = [q.strip() for q in queries if q and q.strip()]

    scopes = list(expansion.scopes) if expansion.scopes else [default_scope]

    dense = multi_query_vector_search(
        queries,
        limit=dense_k,
        # Soft tenancy only when explicitly set; category filter stays on
        # the keyword channel so Atlas index filter-fields are optional.
        apply_metadata_filter=False,
    )

    sparse = keyword_search(
        keywords=expansion.keywords,
        query_text=expansion.search_query,
        categories=list(expansion.categories),
        policy_ids=list(expansion.policy_ids),
        scopes=scopes,
        limit=sparse_k,
        use_metadata_filter=True,
    )

    fused = rerank(dense_results=dense, sparse_results=sparse)
    chunks = [citation_view(doc) for doc in fused]

    return RetrievalResult(
        expansion=expansion_to_dict(expansion),
        dense_results=dense,
        sparse_results=sparse,
        chunks=chunks,
    )
