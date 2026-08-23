"""Keyword retrieval with metadata filters + BM25 scoring."""

from __future__ import annotations

import re
from typing import Any

from rank_bm25 import BM25Okapi

from src.utils.config import get_app_config
from src.utils.mongo import get_documents_collection

_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.IGNORECASE)

PROJECTION = {
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
    "policy_ids_mentioned": 1,
}


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


def build_metadata_filter(
    *,
    categories: list[str] | None = None,
    policy_ids: list[str] | None = None,
    scopes: list[str] | None = None,
) -> dict[str, Any]:
    """Mongo filter from inferred expansion metadata (AND of ORs)."""
    clauses: list[dict[str, Any]] = []
    if categories:
        clauses.append({"category": {"$in": list(categories)}})
    if policy_ids:
        clauses.append(
            {
                "$or": [
                    {"policy_id": {"$in": list(policy_ids)}},
                    {"policy_ids_mentioned": {"$in": list(policy_ids)}},
                ]
            }
        )
    if scopes:
        clauses.append({"scope": {"$in": list(scopes)}})

    if not clauses:
        return {}
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def keyword_search(
    *,
    keywords: list[str],
    query_text: str = "",
    categories: list[str] | None = None,
    policy_ids: list[str] | None = None,
    scopes: list[str] | None = None,
    limit: int | None = None,
    use_metadata_filter: bool = True,
) -> list[dict[str, Any]]:
    """
    Fetch chunks (optionally metadata-filtered), score with BM25 on keywords.

    Returns docs with ``score`` (BM25) and ``channel`` = ``keyword``.
    """
    cfg = get_app_config()["retrieval"]
    limit = limit if limit is not None else int(cfg.get("sparse_top_k", 12))

    mongo_filter: dict[str, Any] = {}
    if use_metadata_filter:
        mongo_filter = build_metadata_filter(
            categories=categories,
            policy_ids=policy_ids,
            scopes=scopes,
        )

    collection = get_documents_collection()
    candidates = list(collection.find(mongo_filter, projection=PROJECTION))

    # If a tight filter returned nothing, fall back to unfiltered so recall
    # is not wiped out by a wrong category guess.
    if not candidates and mongo_filter:
        candidates = list(collection.find({}, projection=PROJECTION))

    if not candidates:
        return []

    query_tokens = _tokenize(" ".join(keywords) + " " + query_text)
    if not query_tokens:
        # No lexical signal — return metadata hits in stored order
        out = []
        for doc in candidates[:limit]:
            hit = dict(doc)
            hit["score"] = 0.0
            hit["channel"] = "keyword"
            out.append(hit)
        return out

    corpus = [
        _tokenize(
            f"{doc.get('section_title', '')} {doc.get('policy_id', '')} "
            f"{doc.get('content', '')}"
        )
        for doc in candidates
    ]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(query_tokens)

    ranked = sorted(
        zip(candidates, scores, strict=True),
        key=lambda pair: pair[1],
        reverse=True,
    )

    results: list[dict[str, Any]] = []
    for doc, score in ranked[:limit]:
        if score <= 0 and keywords:
            continue
        hit = dict(doc)
        hit["score"] = float(score)
        hit["channel"] = "keyword"
        results.append(hit)

    # If BM25 zeroed everything (rare), still surface metadata-filtered docs
    if not results and candidates:
        for doc in candidates[:limit]:
            hit = dict(doc)
            hit["score"] = 0.0
            hit["channel"] = "keyword"
            results.append(hit)

    return results
