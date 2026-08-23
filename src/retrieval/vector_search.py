"""MongoDB Atlas $vectorSearch over KB chunk embeddings."""

from __future__ import annotations

import argparse
from typing import Any

from src.utils.config import get_app_config, get_mongodb_collection, get_mongodb_database
from src.utils.embeddings import embed_query
from src.utils.mongo import get_documents_collection

VECTOR_INDEX_NAME = "vector_index"
VECTOR_PATH = "embedd"

PROJECTION_FIELDS = {
    "_id": 0,
    "chunk_id": 1,
    "doc_id": 1,
    "policy_id": 1,
    "category": 1,
    "scope": 1,
    "section_title": 1,
    "heading_path": 1,
    "source_file": 1,
    "content": 1,
    "score": {"$meta": "vectorSearchScore"},
}


def _atlas_filter(
    *,
    categories: list[str] | None = None,
    policy_ids: list[str] | None = None,
    scopes: list[str] | None = None,
) -> dict[str, Any] | None:
    """
    Optional Atlas $vectorSearch.filter.

    Requires those fields to be listed as filter-type fields on the Atlas
    vector index. Callers that are unsure should leave filters empty and
    rely on the keyword channel instead.
    """
    clauses: list[dict[str, Any]] = []
    if categories:
        clauses.append({"category": {"$in": list(categories)}})
    if policy_ids:
        clauses.append({"policy_id": {"$in": list(policy_ids)}})
    if scopes:
        clauses.append({"scope": {"$in": list(scopes)}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def vector_search(
    query: str,
    *,
    limit: int | None = None,
    num_candidates: int | None = None,
    index: str = VECTOR_INDEX_NAME,
    path: str = VECTOR_PATH,
    categories: list[str] | None = None,
    policy_ids: list[str] | None = None,
    scopes: list[str] | None = None,
    apply_metadata_filter: bool = False,
) -> list[dict[str, Any]]:
    """
    Embed ``query`` with BGE-small and run Atlas ``$vectorSearch`` on ``embedd``.

    Returns matching documents with ``score`` (vectorSearchScore) and
    ``channel`` = ``vector``.
    """
    cfg = get_app_config()["retrieval"]
    limit = limit if limit is not None else int(cfg.get("dense_top_k", 12))
    if num_candidates is None:
        num_candidates = max(limit * 10, int(cfg.get("dense_top_k", 12)))

    query_vector = embed_query(query)
    collection = get_documents_collection()

    search_stage: dict[str, Any] = {
        "index": index,
        "path": path,
        "queryVector": query_vector,
        "numCandidates": num_candidates,
        "limit": limit,
    }
    if apply_metadata_filter:
        atlas_filter = _atlas_filter(
            categories=categories, policy_ids=policy_ids, scopes=scopes
        )
        if atlas_filter:
            search_stage["filter"] = atlas_filter

    pipeline = [
        {"$vectorSearch": search_stage},
        {"$project": PROJECTION_FIELDS},
    ]

    results = []
    for doc in collection.aggregate(pipeline):
        hit = dict(doc)
        hit["channel"] = "vector"
        results.append(hit)
    return results


def multi_query_vector_search(
    queries: list[str],
    *,
    limit: int | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """
    Run ``vector_search`` for each query and merge by best score per chunk_id.

    Preserves rank order by descending score for downstream RRF.
    """
    if not queries:
        return []

    cfg = get_app_config()["retrieval"]
    limit = limit if limit is not None else int(cfg.get("dense_top_k", 12))

    best: dict[str, dict[str, Any]] = {}
    for query in queries:
        query = (query or "").strip()
        if not query:
            continue
        for doc in vector_search(query, limit=limit, **kwargs):
            chunk_id = doc.get("chunk_id")
            if not chunk_id:
                continue
            prev = best.get(chunk_id)
            if prev is None or float(doc.get("score") or 0) > float(
                prev.get("score") or 0
            ):
                best[chunk_id] = doc

    ranked = sorted(
        best.values(),
        key=lambda d: float(d.get("score") or 0),
        reverse=True,
    )
    return ranked[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sample Atlas $vectorSearch query against KB embedd field"
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="How long do I have to return an item?",
        help="Natural-language search query",
    )
    parser.add_argument("--limit", type=int, default=5, help="Number of results")
    parser.add_argument(
        "--num-candidates",
        type=int,
        default=None,
        help="ANN candidates (default: max(limit*10, dense_top_k))",
    )
    parser.add_argument(
        "--category",
        action="append",
        default=None,
        help="Optional category filter (repeatable); requires Atlas filter fields",
    )
    args = parser.parse_args()

    print(f"Target: {get_mongodb_database()}.{get_mongodb_collection()}")
    print(f"Index: {VECTOR_INDEX_NAME} | path: {VECTOR_PATH}")
    print(f"Query: {args.query!r}\n")

    results = vector_search(
        args.query,
        limit=args.limit,
        num_candidates=args.num_candidates,
        categories=args.category,
        apply_metadata_filter=bool(args.category),
    )

    if not results:
        print("No results. Check that vector_index exists and embedd is indexed.")
        return

    for i, doc in enumerate(results, start=1):
        preview = (doc.get("content") or "").replace("\n", " ")[:160]
        print(
            f"{i}. score={doc.get('score', 0):.4f} | "
            f"{doc.get('chunk_id')} | {doc.get('policy_id')} | "
            f"{doc.get('section_title')}"
        )
        print(f"   {preview}...\n")


if __name__ == "__main__":
    main()
