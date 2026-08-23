"""Load escalation policy text for prompt injection when retrieval misses it."""

from __future__ import annotations

from functools import lru_cache

from src.utils.chunking import parse_frontmatter
from src.utils.config import get_app_config, project_path


@lru_cache(maxsize=1)
def load_escalation_policy_text() -> str:
    """Return escalation_criteria.md body (frontmatter stripped)."""
    kb_root = project_path(get_app_config()["paths"]["knowledge_base"])
    path = kb_root / "escalation_criteria.md"
    raw = path.read_text(encoding="utf-8")
    _meta, body = parse_frontmatter(raw)
    return body.strip()


def has_escalation_chunks(chunks: list[dict] | None) -> bool:
    """True when retrieval already returned escalation-category passages."""
    for chunk in chunks or []:
        category = str(chunk.get("category") or "").lower()
        policy_id = str(chunk.get("policy_id") or "").upper()
        if category == "escalation" or policy_id.startswith("ESCALATE"):
            return True
    return False
