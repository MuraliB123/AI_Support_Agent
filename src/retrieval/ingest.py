"""Ingest Markdown KB chunks into MongoDB (no embeddings yet)."""

from __future__ import annotations

import argparse

from src.utils.chunking import chunk_knowledge_base
from src.utils.config import (
    get_app_config,
    get_mongodb_collection,
    get_mongodb_database,
)
from src.utils.mongo import clear_all_chunks, count_chunks, upsert_chunks


def ingest(clear: bool = False) -> dict[str, int | str]:
    if clear:
        deleted = clear_all_chunks()
        print(f"Cleared {deleted} existing chunk(s) from MongoDB.")

    records = chunk_knowledge_base()
    docs = [record.to_mongo_document() for record in records]
    result = upsert_chunks(docs)

    return {
        "database": get_mongodb_database(),
        "collection": get_mongodb_collection(),
        "files_chunked": len({r.source_file for r in records}),
        "chunks_written": len(records),
        "total_in_collection": count_chunks(),
        **result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chunk Nimbus Home KB Markdown and store in MongoDB"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete all existing chunks in the collection before ingest",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk files and print summary without writing to MongoDB",
    )
    args = parser.parse_args()

    app_cfg = get_app_config()
    kb_path = app_cfg["paths"]["knowledge_base"]
    print(f"Knowledge base: {kb_path}")
    print(f"MongoDB target: {get_mongodb_database()}.{get_mongodb_collection()}")

    if args.dry_run:
        records = chunk_knowledge_base()
        print(f"Dry run: {len(records)} chunk(s) from {len({r.source_file for r in records})} file(s)")
        for record in records[:5]:
            print(
                f"  - {record.chunk_id} | {record.section_title} | "
                f"{record.char_count} chars | policies={record.policy_ids_mentioned}"
            )
        if len(records) > 5:
            print(f"  ... and {len(records) - 5} more")
        return

    summary = ingest(clear=args.clear)
    print(
        "Ingest complete: "
        f"{summary['chunks_written']} chunk(s) from {summary['files_chunked']} file(s) "
        f"-> {summary['database']}.{summary['collection']} "
        f"(upserted={summary['upserted']}, modified={summary['modified']}, "
        f"total={summary['total_in_collection']})"
    )


if __name__ == "__main__":
    main()
