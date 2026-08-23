"""Embed existing MongoDB chunks in place (no re-chunking)."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from pymongo import UpdateOne

from src.utils.config import (
    get_model_config,
    get_mongodb_collection,
    get_mongodb_database,
)
from src.utils.embeddings import embed_texts
from src.utils.mongo import get_documents_collection


def embed_existing_chunks(
    *,
    batch_size: int = 32,
    force: bool = False,
) -> dict[str, int | str]:
    """
    Read chunks from MongoDB, embed `content`, set `embedd` on each doc in place.

    By default skips documents that already have a non-empty `embedd` unless
    ``force=True``.
    """
    collection = get_documents_collection()
    model_name = get_model_config()["embeddings"]["model"]
    dimensions = get_model_config()["embeddings"]["dimensions"]

    query: dict = {"content": {"$exists": True, "$ne": ""}}
    if not force:
        query["$or"] = [
            {"embedd": {"$exists": False}},
            {"embedd": None},
            {"embedd": []},
        ]

    cursor = collection.find(
        query,
        projection={"_id": 1, "chunk_id": 1, "content": 1},
    )
    docs = list(cursor)
    if not docs:
        return {
            "database": get_mongodb_database(),
            "collection": get_mongodb_collection(),
            "model": model_name,
            "dimensions": dimensions,
            "scanned": 0,
            "updated": 0,
            "batches": 0,
        }

    updated = 0
    batches = 0
    now = datetime.now(UTC)

    for start in range(0, len(docs), batch_size):
        batch = docs[start : start + batch_size]
        texts = [doc["content"] for doc in batch]
        vectors = embed_texts(texts)

        if len(vectors) != len(batch):
            raise RuntimeError(
                f"Embedding count mismatch: got {len(vectors)} for {len(batch)} docs"
            )

        operations = [
            UpdateOne(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "embedd": vector,
                        "embedding_model": model_name,
                        "embedding_dims": len(vector),
                        "updated_at": now,
                    }
                },
            )
            for doc, vector in zip(batch, vectors, strict=True)
        ]
        result = collection.bulk_write(operations, ordered=False)
        updated += result.modified_count
        batches += 1
        print(
            f"  Batch {batches}: embedded {len(batch)} chunk(s) "
            f"(modified={result.modified_count})"
        )

    return {
        "database": get_mongodb_database(),
        "collection": get_mongodb_collection(),
        "model": model_name,
        "dimensions": dimensions,
        "scanned": len(docs),
        "updated": updated,
        "batches": batches,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Embed existing MongoDB KB chunks in place (key: embedd)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed even if embedd already exists",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Number of chunks to embed per batch (default: 32)",
    )
    args = parser.parse_args()

    print(
        f"Target: {get_mongodb_database()}.{get_mongodb_collection()} "
        f"| model={get_model_config()['embeddings']['model']}"
    )
    print("Loading embedding model (first run may download weights)...")
    summary = embed_existing_chunks(batch_size=args.batch_size, force=args.force)
    print(
        "Embed complete: "
        f"scanned={summary['scanned']}, updated={summary['updated']}, "
        f"batches={summary['batches']}, dims={summary['dimensions']}"
    )


if __name__ == "__main__":
    main()
