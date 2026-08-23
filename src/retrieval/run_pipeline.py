"""CLI: run the hybrid retrieval pipeline against a sample ticket context."""

from __future__ import annotations

import argparse
import json

from src.retrieval.pipeline import run_retrieval_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Expand → vector + keyword/metadata → RRF (Phase 4)"
    )
    parser.add_argument(
        "--subject",
        default="Refund for damaged kettle",
        help="Ticket subject",
    )
    parser.add_argument(
        "--summary",
        default=(
            "Customer received a cracked electric kettle on order NH-4471 "
            "delivered three days ago and wants a refund or replacement."
        ),
        help="Intake context summary",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON result",
    )
    args = parser.parse_args()

    print("Running retrieval pipeline (loads BGE on first call)...\n")
    result = run_retrieval_pipeline(subject=args.subject, context_summary=args.summary)

    expansion = result.expansion
    print("Expansion")
    print(f"  search_query: {expansion.get('search_query')}")
    print(f"  alternates:   {expansion.get('alternate_queries')}")
    print(f"  keywords:     {expansion.get('keywords')}")
    print(f"  categories:   {expansion.get('categories')}")
    print(f"  policy_ids:   {expansion.get('policy_ids')}")
    print(f"  rationale:    {expansion.get('rationale')}")
    print(
        f"\nHits: dense={len(result.dense_results)} "
        f"sparse={len(result.sparse_results)} fused={len(result.chunks)}\n"
    )

    for i, chunk in enumerate(result.chunks, start=1):
        preview = (chunk.get("content") or "").replace("\n", " ")[:140]
        print(
            f"{i}. rrf={chunk.get('rrf_score', 0):.4f} | "
            f"{chunk.get('chunk_id')} | {chunk.get('policy_id')} | "
            f"{chunk.get('section_title')} | ranks={chunk.get('rrf_ranks')}"
        )
        print(f"   {preview}...\n")

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, default=str))


if __name__ == "__main__":
    main()
