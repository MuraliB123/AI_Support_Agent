"""MongoDB helpers for KB chunk storage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import ASCENDING, MongoClient, ReplaceOne
from pymongo.collection import Collection
from pymongo.server_api import ServerApi

from src.utils.config import (
    get_mongodb_collection,
    get_mongodb_database,
    get_mongodb_uri,
)

_client: MongoClient | None = None


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(get_mongodb_uri(), server_api=ServerApi("1"))
    return _client


def get_documents_collection() -> Collection:
    client = get_mongo_client()
    db = client[get_mongodb_database()]
    collection = db[get_mongodb_collection()]
    collection.create_index([("chunk_id", ASCENDING)], unique=True)
    collection.create_index([("policy_id", ASCENDING)])
    collection.create_index([("category", ASCENDING)])
    collection.create_index([("scope", ASCENDING)])
    collection.create_index([("doc_id", ASCENDING)])
    return collection


def upsert_chunks(chunks: list[dict[str, Any]]) -> dict[str, int]:
    """Upsert chunk documents into MongoDB. Returns inserted/updated counts."""
    if not chunks:
        return {"matched": 0, "modified": 0, "upserted": 0}

    collection = get_documents_collection()
    now = datetime.now(UTC)
    operations: list[ReplaceOne] = []

    for chunk in chunks:
        doc = {**chunk, "updated_at": now}
        if "created_at" not in doc:
            doc["created_at"] = now
        operations.append(
            ReplaceOne({"chunk_id": doc["chunk_id"]}, doc, upsert=True)
        )

    result = collection.bulk_write(operations, ordered=False)
    return {
        "matched": result.matched_count,
        "modified": result.modified_count,
        "upserted": result.upserted_count,
    }


def clear_chunks_for_doc(doc_id: str) -> int:
    collection = get_documents_collection()
    result = collection.delete_many({"doc_id": doc_id})
    return result.deleted_count


def clear_all_chunks() -> int:
    collection = get_documents_collection()
    result = collection.delete_many({})
    return result.deleted_count


def count_chunks() -> int:
    return get_documents_collection().count_documents({})
