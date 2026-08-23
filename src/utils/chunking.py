"""Markdown KB chunking with LangChain splitters and search metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from src.utils.config import get_app_config, project_path

HEADER_LEVELS = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
]

POLICY_ID_PATTERN = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+\b")


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    doc_id: str
    policy_id: str
    category: str
    scope: str
    version: str
    effective_date: str
    source_path: str
    source_file: str
    chunk_index: int
    heading_path: list[str]
    section_title: str
    content: str
    policy_ids_mentioned: list[str]
    char_count: int

    def to_mongo_document(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "policy_id": self.policy_id,
            "category": self.category,
            "scope": self.scope,
            "version": self.version,
            "effective_date": self.effective_date,
            "source_path": self.source_path,
            "source_file": self.source_file,
            "chunk_index": self.chunk_index,
            "heading_path": self.heading_path,
            "section_title": self.section_title,
            "content": self.content,
            "policy_ids_mentioned": self.policy_ids_mentioned,
            "char_count": self.char_count,
        }


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    metadata = yaml.safe_load(parts[1]) or {}
    if not isinstance(metadata, dict):
        raise ValueError("Frontmatter must be a YAML mapping")
    body = parts[2].lstrip("\n")
    return metadata, body


def _heading_path_from_metadata(metadata: dict[str, Any]) -> list[str]:
    path: list[str] = []
    for _, key in HEADER_LEVELS:
        value = metadata.get(key)
        if value:
            path.append(str(value).strip())
    return path


def _section_title(heading_path: list[str], doc_title: str) -> str:
    if heading_path:
        return heading_path[-1]
    return doc_title


def _extract_policy_ids(text: str) -> list[str]:
    found = POLICY_ID_PATTERN.findall(text)
    return sorted(set(found))


def _build_splitters() -> tuple[MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter, int]:
    cfg = get_app_config()["chunking"]
    max_tokens = cfg.get("target_tokens_max", 800)
    overlap_ratio = cfg.get("overlap_ratio", 0.12)

    # Rough token estimate: ~4 characters per token for English prose
    chunk_size = int(max_tokens * 4)
    chunk_overlap = int(chunk_size * overlap_ratio)

    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADER_LEVELS,
        strip_headers=False,
    )
    size_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )
    return header_splitter, size_splitter, chunk_size


def chunk_markdown_file(path: Path, kb_root: Path | None = None) -> list[ChunkRecord]:
    """Split one Markdown KB file into metadata-rich chunks."""
    kb_root = kb_root or project_path(get_app_config()["paths"]["knowledge_base"])
    raw = path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(raw)

    doc_id = str(frontmatter.get("doc_id") or path.stem)
    policy_id = str(frontmatter.get("policy_id") or "")
    category = str(frontmatter.get("category") or "general")
    scope = str(frontmatter.get("scope") or "global")
    version = str(frontmatter.get("version") or "1.0")
    effective_date = str(frontmatter.get("effective_date") or "")

    relative_source = str(path.resolve().relative_to(project_path().resolve())).replace(
        "\\", "/"
    )
    header_splitter, size_splitter, max_chunk_chars = _build_splitters()
    header_docs = header_splitter.split_text(body)

    sized_docs: list[Document] = []
    for doc in header_docs:
        if len(doc.page_content.strip()) <= max_chunk_chars:
            sized_docs.append(doc)
        else:
            sized_docs.extend(size_splitter.split_documents([doc]))

    doc_title = _heading_path_from_metadata(header_docs[0].metadata)[0] if header_docs else path.stem
    records: list[ChunkRecord] = []

    for index, doc in enumerate(sized_docs):
        content = doc.page_content.strip()
        if not content:
            continue

        heading_path = _heading_path_from_metadata(doc.metadata)
        section_title = _section_title(heading_path, doc_title)
        mentioned = _extract_policy_ids(content)
        if policy_id and policy_id not in mentioned:
            mentioned = sorted(set(mentioned + [policy_id]))

        records.append(
            ChunkRecord(
                chunk_id=f"{doc_id}::{index}",
                doc_id=doc_id,
                policy_id=policy_id,
                category=category,
                scope=scope,
                version=version,
                effective_date=effective_date,
                source_path=relative_source,
                source_file=path.name,
                chunk_index=index,
                heading_path=heading_path,
                section_title=section_title,
                content=content,
                policy_ids_mentioned=mentioned,
                char_count=len(content),
            )
        )

    return records


def chunk_knowledge_base(kb_dir: Path | None = None) -> list[ChunkRecord]:
    """Chunk all Markdown files in the knowledge base directory."""
    kb_dir = kb_dir or project_path(get_app_config()["paths"]["knowledge_base"])
    if not kb_dir.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {kb_dir}")

    all_records: list[ChunkRecord] = []
    md_files = sorted(kb_dir.glob("*.md"))
    if not md_files:
        raise FileNotFoundError(f"No Markdown files found in {kb_dir}")

    for md_file in md_files:
        all_records.extend(chunk_markdown_file(md_file, kb_root=kb_dir))

    return all_records
